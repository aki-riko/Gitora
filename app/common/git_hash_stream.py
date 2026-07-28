# coding: utf-8
"""流式读取 Git 命令输出的提交哈希，并支持协作取消。"""
from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO


_COMMIT_HASH_RE = re.compile(rb"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})")


@dataclass(frozen=True)
class GitHashStreamResult:
    success: bool
    hashes: list[str]
    error: str = ""
    cancelled: bool = False


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=0.2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=0.2)


def _read_available(stream: BinaryIO) -> list[bytes]:
    chunks: list[bytes] = []
    while True:
        try:
            chunk = os.read(stream.fileno(), 4096)
        except BlockingIOError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return chunks


class _GitHashStream:
    def __init__(
        self,
        command: list[str],
        cwd: str,
        timeout: float,
        creationflags: int,
        cancel_requested: Callable[[], bool],
        on_progress: Callable[[list[str]], None] | None,
    ) -> None:
        self._command = command
        self._cwd = cwd
        self._timeout = timeout
        self._creationflags = creationflags
        self._cancel_requested = cancel_requested
        self._on_progress = on_progress
        self._hashes: list[str] = []
        self._seen: set[str] = set()
        self._stdout_pending = b""
        self._stderr: list[bytes] = []

    def run(self) -> GitHashStreamResult:
        try:
            process = self._start_process()
        except (FileNotFoundError, OSError) as exc:
            return GitHashStreamResult(False, [], str(exc))

        assert process.stdout is not None
        assert process.stderr is not None
        try:
            os.set_blocking(process.stdout.fileno(), False)
            os.set_blocking(process.stderr.fileno(), False)
            state = self._wait_for_process(process)
        except BaseException:
            _stop_process(process)
            raise
        finally:
            process.stdout.close()
            process.stderr.close()

        error = b"".join(self._stderr).decode("utf-8", "replace")
        if state == "cancelled":
            return GitHashStreamResult(False, self._hashes, error, True)
        if state == "timeout":
            return GitHashStreamResult(
                False, self._hashes, f"操作超时（{self._timeout:g}秒）"
            )
        return GitHashStreamResult(process.returncode == 0, self._hashes, error)

    def _start_process(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            self._command,
            cwd=self._cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=self._creationflags,
        )

    def _wait_for_process(self, process: subprocess.Popen[bytes]) -> str:
        assert process.stdout is not None
        assert process.stderr is not None
        deadline = time.monotonic() + self._timeout
        while process.poll() is None:
            if self._cancel_requested():
                _stop_process(process)
                return "cancelled"
            self._drain_stdout(process.stdout)
            self._stderr.extend(_read_available(process.stderr))
            if time.monotonic() >= deadline:
                _stop_process(process)
                return "timeout"
            time.sleep(0.05)

        if self._cancel_requested():
            return "cancelled"
        self._drain_stdout(process.stdout, final=True)
        self._stderr.extend(_read_available(process.stderr))
        return "finished"

    def _drain_stdout(self, stream: BinaryIO, final: bool = False) -> None:
        chunks = _read_available(stream)
        if not chunks and not (final and self._stdout_pending):
            return
        lines = (self._stdout_pending + b"".join(chunks)).split(b"\n")
        self._stdout_pending = b"" if final else lines.pop()
        changed = False
        for raw_line in lines:
            line = raw_line.strip()
            if not _COMMIT_HASH_RE.fullmatch(line):
                continue
            hash_value = line.decode("ascii")
            if hash_value in self._seen:
                continue
            self._seen.add(hash_value)
            self._hashes.append(hash_value)
            changed = True
        if changed and self._on_progress is not None:
            self._on_progress(list(self._hashes))


def stream_git_hashes(
    command: list[str],
    cwd: str,
    *,
    timeout: float = 30,
    creationflags: int = 0,
    cancel_requested: Callable[[], bool] = lambda: False,
    on_progress: Callable[[list[str]], None] | None = None,
) -> GitHashStreamResult:
    """运行 Git 命令，并在哈希出现时发布累计候选。"""
    if cancel_requested():
        return GitHashStreamResult(False, [], cancelled=True)
    return _GitHashStream(
        command,
        cwd,
        timeout,
        creationflags,
        cancel_requested,
        on_progress,
    ).run()


__all__ = ["GitHashStreamResult", "stream_git_hashes"]
