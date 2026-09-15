# coding: utf-8
"""Git push 的实时进度解析与流式进程执行。"""
from __future__ import annotations

import asyncio
import codecs
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

from .logger import get_logger

logger = get_logger("GitPushProgress")

# 超时后的清理宽限期。只用于等待"杀进程树 + 关管道"生效，不参与业务超时判定。
# 只杀顶层 git.exe 时，git 派生的 ssh / git-remote-https / 凭据助手会继续持有
# stdout/stderr 管道写端，读取任务永远等不到 EOF，后台线程会被永久钉死
# （表现：进度停在某个百分比、operationBusy 恒为 true、日志再无输出）。
_CLEANUP_GRACE_SECONDS = 5.0
_KILL_TREE_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class PushProgress:
    percent: int
    message: str


@dataclass(frozen=True)
class PushProcessResult:
    success: bool
    stdout: str
    stderr: str


_PROGRESS_LINE = re.compile(
    r"^(?P<remote>remote:\s*)?"
    r"(?P<phase>Enumerating objects|Counting objects|Compressing objects|"
    r"Writing objects|Resolving deltas):\s*"
    r"(?P<percent>\d{1,3})%\s*"
    r"\((?P<current>\d+)/(?P<total>\d+)\)(?P<suffix>.*)$",
    re.IGNORECASE,
)
_ENUMERATING_LINE = re.compile(
    r"^Enumerating objects:\s*(?P<count>\d+)(?:,\s*done\.)?$",
    re.IGNORECASE,
)
_TRANSFER_DETAIL = re.compile(r",\s*(?P<size>[^,|]+?)\s*\|\s*(?P<speed>[^,]+)")
_PHASE_RANGES = {
    "enumerating objects": (1, 5),
    "counting objects": (5, 25),
    "compressing objects": (25, 45),
    "writing objects": (45, 95),
    "resolving deltas": (95, 99),
}
_PHASE_LABELS = {
    "enumerating objects": "正在枚举对象",
    "counting objects": "正在计数对象",
    "compressing objects": "正在压缩对象",
    "writing objects": "正在写入对象",
    "resolving deltas": "远端正在解析增量",
}


class GitPushProgressParser:
    """把 Git 各阶段的局部百分比转换为单调的全局百分比。"""

    def __init__(self) -> None:
        self._last_percent = 0
        self._last_message = ""

    def feed(self, line: str) -> PushProgress | None:
        clean = line.strip()
        match = _PROGRESS_LINE.match(clean)
        if match:
            return self._from_percentage(match)
        return self._from_status_line(clean)

    def _from_percentage(self, match: re.Match[str]) -> PushProgress | None:
        phase = match.group("phase").lower()
        phase_percent = min(100, int(match.group("percent")))
        start, end = _PHASE_RANGES[phase]
        percent = start + round((end - start) * phase_percent / 100)
        message = self._format_message(phase, match)
        return self._new_update(percent, message)

    def _from_status_line(self, line: str) -> PushProgress | None:
        enumerating = _ENUMERATING_LINE.match(line)
        if enumerating:
            return self._new_update(
                3, f"正在枚举对象 {enumerating.group('count')}"
            )
        if line.lower().startswith("delta compression using"):
            return self._new_update(25, "正在准备压缩对象")
        if line.lower() == "everything up-to-date":
            return self._new_update(99, "远端已是最新")
        return None

    @staticmethod
    def _format_message(phase: str, match: re.Match[str]) -> str:
        message = (
            f"{_PHASE_LABELS[phase]} "
            f"{match.group('current')}/{match.group('total')}"
        )
        detail = _TRANSFER_DETAIL.search(match.group("suffix") or "")
        if detail and phase == "writing objects":
            message += f" · {detail.group('size').strip()} · {detail.group('speed').strip()}"
        return message

    def _new_update(self, percent: int, message: str) -> PushProgress | None:
        percent = max(self._last_percent, min(99, percent))
        if percent == self._last_percent and message == self._last_message:
            return None
        self._last_percent = percent
        self._last_message = message
        return PushProgress(percent, message)


async def _read_plain_stream(
    stream: asyncio.StreamReader, chunks: list[str]
) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while chunk := await stream.read(4096):
        chunks.append(decoder.decode(chunk))
    tail = decoder.decode(b"", final=True)
    if tail:
        chunks.append(tail)


async def _read_progress_stream(
    stream: asyncio.StreamReader,
    chunks: list[str],
    on_progress: Callable[[int, str], None],
) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    parser = GitPushProgressParser()
    pending = ""
    while chunk := await stream.read(4096):
        text = decoder.decode(chunk)
        chunks.append(text)
        pending = _publish_complete_progress_lines(
            pending + text, parser, on_progress
        )
    tail = decoder.decode(b"", final=True)
    if tail:
        chunks.append(tail)
        pending += tail
    if pending:
        _publish_progress_line(pending, parser, on_progress)


def _publish_complete_progress_lines(
    text: str,
    parser: GitPushProgressParser,
    on_progress: Callable[[int, str], None],
) -> str:
    parts = re.split(r"[\r\n]", text)
    for line in parts[:-1]:
        _publish_progress_line(line, parser, on_progress)
    return parts[-1]


def _publish_progress_line(
    line: str,
    parser: GitPushProgressParser,
    on_progress: Callable[[int, str], None],
) -> None:
    update = parser.feed(line)
    if update is not None:
        on_progress(update.percent, update.message)


def _push_child_env() -> dict[str, str]:
    """构造 push 子进程环境：关闭"会无声挂住"的交互式提示。

    GUI 进程没有可交互终端：git 的终端凭据提示会直接写到 /dev/tty，界面完全看不到，
    进程就停在那里等输入。这里只关掉这类提示，让它们快速失败；
    GIT_ASKPASS / 凭据助手等**非交互**取凭据的路径保持原样不动。
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    # 调用方没显式指定 ssh 命令时，禁用 ssh 交互提示并给 TCP 连接一个上限；
    # 否则需要口令/键盘交互的 ssh 会以同样的方式无声挂住。git 仍会按 URL 追加端口。
    if "GIT_SSH_COMMAND" not in env and "GIT_SSH" not in env:
        env["GIT_SSH_COMMAND"] = "ssh -o BatchMode=yes -o ConnectTimeout=30"
    return env


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    """杀掉整棵进程树，而不是只终止顶层 git.exe。

    子进程（ssh / git-remote-https / 凭据助手）会继承 stdout/stderr 管道写端，
    只杀 git.exe 的话它们仍然让管道保持打开，读取端永远等不到 EOF。
    """
    pid = process.pid
    if os.name == "nt" and pid:
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill", "/F", "/T", "/PID", str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            await asyncio.wait_for(
                killer.wait(), timeout=_KILL_TREE_TIMEOUT_SECONDS
            )
        except (OSError, subprocess.SubprocessError, TimeoutError):
            logger.warning("taskkill 清理 Git 子进程树失败，回退为直接终止", exc_info=True)
    try:
        process.kill()
    except OSError:
        pass


async def _await_bounded(awaitable, timeout: float) -> bool:
    """在限定时间内等待；超时即取消并返回 False。清理路径绝不允许无界等待。"""
    try:
        await asyncio.wait_for(awaitable, timeout=timeout)
        return True
    except TimeoutError:
        return False
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        return False


def _close_pipe_readers(process: asyncio.subprocess.Process) -> None:
    """关闭读管道，让 Proactor 上挂起的 ReadFile 立即结束。

    否则事件循环关闭时会在未完成的 overlapped 操作上空转（``IocpProactor.close``
    的 ``while self._cache``），同样表现为卡死。
    """
    transport_owner = getattr(process, "_transport", None)
    for fd in (1, 2):
        transport = None
        if transport_owner is not None:
            try:
                transport = transport_owner.get_pipe_transport(fd)
            except (AttributeError, RuntimeError):
                transport = None
        if transport is None:
            continue
        try:
            transport.close()
        except (RuntimeError, OSError):
            pass


async def _run_git_push(
    command: list[str],
    cwd: str,
    timeout: int,
    on_progress: Callable[[int, str], None],
) -> PushProcessResult:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_push_child_env(),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stdout_reader = asyncio.create_task(
        _read_plain_stream(process.stdout, stdout_chunks)
    )
    stderr_reader = asyncio.create_task(
        _read_progress_stream(process.stderr, stderr_chunks, on_progress)
    )
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except TimeoutError:
        timed_out = True
        await _kill_process_tree(process)
        await _await_bounded(process.wait(), _CLEANUP_GRACE_SECONDS)
    readers_done = await _await_bounded(
        asyncio.gather(stdout_reader, stderr_reader, return_exceptions=True),
        _CLEANUP_GRACE_SECONDS,
    )
    if not readers_done:
        # 仍有子进程持有管道写端：放弃剩余输出并关掉读端，避免后台线程被永久钉死。
        logger.warning(
            "Git push 结束后管道仍被占用，放弃读取输出: %s", " ".join(command)
        )
        stdout_reader.cancel()
        stderr_reader.cancel()
        _close_pipe_readers(process)
    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    if timed_out:
        return PushProcessResult(
            False,
            stdout,
            f"操作超时（{timeout}秒），可能是网络问题或仓库过大",
        )
    return PushProcessResult(process.returncode == 0, stdout, stderr)


def run_git_push_with_progress(
    command: list[str],
    cwd: str,
    timeout: int,
    on_progress: Callable[[int, str], None],
) -> PushProcessResult:
    """执行 push 并实时回传 Git stderr 中的确定进度。"""
    try:
        return asyncio.run(_run_git_push(command, cwd, timeout, on_progress))
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        logger.exception(f"启动 Git push 失败: {' '.join(command)}")
        return PushProcessResult(False, "", str(exc))
