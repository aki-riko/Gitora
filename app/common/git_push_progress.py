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


async def _run_git_push(
    command: list[str],
    cwd: str,
    timeout: int,
    on_progress: Callable[[int, str], None],
) -> PushProcessResult:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
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
        process.kill()
        await process.wait()
    await asyncio.gather(stdout_reader, stderr_reader)
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
