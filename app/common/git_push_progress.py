# coding: utf-8
"""Git push 的实时进度解析与流式进程执行。"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, TextIO

from PySide6.QtCore import QThread, Signal

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


def _read_plain_stream(stream: TextIO, chunks: list[str]) -> None:
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            chunks.append(chunk)
    except (OSError, ValueError) as exc:
        logger.warning(f"读取 Git push stdout 失败: {exc}")


def _read_progress_stream(
    stream: TextIO,
    chunks: list[str],
    updates: queue.Queue[PushProgress],
) -> None:
    parser = GitPushProgressParser()
    line_chars: list[str] = []
    try:
        while True:
            char = stream.read(1)
            if not char:
                _parse_progress_line(line_chars, parser, updates)
                return
            chunks.append(char)
            if char in "\r\n":
                _parse_progress_line(line_chars, parser, updates)
                line_chars.clear()
            else:
                line_chars.append(char)
    except (OSError, ValueError) as exc:
        logger.warning(f"读取 Git push stderr 失败: {exc}")


def _parse_progress_line(
    line_chars: list[str],
    parser: GitPushProgressParser,
    updates: queue.Queue[PushProgress],
) -> None:
    if not line_chars:
        return
    update = parser.feed("".join(line_chars))
    if update:
        updates.put(update)


def _start_reader_threads(
    process: subprocess.Popen[str],
    stdout_chunks: list[str],
    stderr_chunks: list[str],
    updates: queue.Queue[PushProgress],
) -> tuple[threading.Thread, threading.Thread]:
    stdout_thread = threading.Thread(
        target=_read_plain_stream,
        args=(process.stdout, stdout_chunks),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_read_progress_stream,
        args=(process.stderr, stderr_chunks, updates),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    return stdout_thread, stderr_thread


def _monitor_process(
    process: subprocess.Popen[str],
    readers: tuple[threading.Thread, threading.Thread],
    updates: queue.Queue[PushProgress],
    timeout: int,
    on_progress: Callable[[int, str], None],
) -> bool:
    deadline = time.monotonic() + timeout
    timed_out = False
    while process.poll() is None or any(reader.is_alive() for reader in readers):
        if process.poll() is None and time.monotonic() >= deadline:
            process.kill()
            timed_out = True
        _deliver_progress(updates, on_progress)
    _deliver_progress(updates, on_progress, drain=True)
    for reader in readers:
        reader.join(timeout=1)
    return timed_out


def _deliver_progress(
    updates: queue.Queue[PushProgress],
    on_progress: Callable[[int, str], None],
    drain: bool = False,
) -> None:
    wait = 0 if drain else 0.05
    try:
        update = updates.get(timeout=wait)
    except queue.Empty:
        return
    on_progress(update.percent, update.message)
    if drain:
        while not updates.empty():
            update = updates.get_nowait()
            on_progress(update.percent, update.message)


def _start_push_process(
    command: list[str], cwd: str
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def run_git_push_with_progress(
    command: list[str],
    cwd: str,
    timeout: int,
    on_progress: Callable[[int, str], None],
) -> PushProcessResult:
    """执行 push 并实时回传 Git stderr 中的确定进度。"""
    try:
        process = _start_push_process(command, cwd)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.exception(f"启动 Git push 失败: {' '.join(command)}")
        return PushProcessResult(False, "", str(exc))

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    updates: queue.Queue[PushProgress] = queue.Queue()
    readers = _start_reader_threads(process, stdout_chunks, stderr_chunks, updates)
    timed_out = _monitor_process(process, readers, updates, timeout, on_progress)
    stdout = "".join(stdout_chunks)
    stderr = "".join(stderr_chunks)
    if timed_out:
        return PushProcessResult(
            False, stdout, f"操作超时（{timeout}秒），可能是网络问题或仓库过大"
        )
    return PushProcessResult(process.returncode == 0, stdout, stderr)


class GitPushWorker(QThread):
    """只用于 Git push，避免改变其他异步 Git 命令的成熟路径。"""

    progress = Signal(int, str)
    finished = Signal(bool, str, str)

    def __init__(self, command: list[str], cwd: str, timeout: int, parent=None):
        super().__init__(parent)
        self.command = command
        self.cwd = cwd
        self.timeout = timeout

    def run(self) -> None:
        result = run_git_push_with_progress(
            self.command, self.cwd, self.timeout, self.progress.emit
        )
        self.finished.emit(result.success, result.stdout, result.stderr)
