# coding: utf-8
from __future__ import annotations

import os
import sys
import threading
import time
import unittest

from app.common.git_hash_stream import stream_git_hashes


class GitHashStreamTest(unittest.TestCase):
    def test_progress_arrives_before_process_finishes(self) -> None:
        commit_hash = "a" * 40
        command = [
            sys.executable,
            "-c",
            (
                "import time; "
                f"print('{commit_hash}', flush=True); "
                "time.sleep(0.4)"
            ),
        ]
        progress_times: list[float] = []
        started = time.monotonic()

        result = stream_git_hashes(
            command,
            os.getcwd(),
            timeout=2,
            on_progress=lambda _hashes: progress_times.append(time.monotonic()),
        )
        finished = time.monotonic()

        self.assertTrue(result.success)
        self.assertEqual(result.hashes, [commit_hash])
        self.assertTrue(progress_times)
        self.assertLess(progress_times[0] - started, finished - started - 0.2)

    def test_cancellation_terminates_running_process(self) -> None:
        commit_hash = "b" * 40
        cancel_requested = threading.Event()
        command = [
            sys.executable,
            "-c",
            (
                "import time; "
                f"print('{commit_hash}', flush=True); "
                "time.sleep(5)"
            ),
        ]
        started = time.monotonic()

        result = stream_git_hashes(
            command,
            os.getcwd(),
            timeout=10,
            cancel_requested=cancel_requested.is_set,
            on_progress=lambda _hashes: cancel_requested.set(),
        )

        self.assertTrue(result.cancelled)
        self.assertEqual(result.hashes, [commit_hash])
        self.assertLess(time.monotonic() - started, 2)

    def test_pre_cancelled_stream_does_not_publish_late_progress(self) -> None:
        commit_hash = "c" * 40
        progress: list[list[str]] = []
        command = [
            sys.executable,
            "-c",
            (
                f"print('{commit_hash}', flush=True); "
                "__import__('time').sleep(5)"
            ),
        ]

        result = stream_git_hashes(
            command,
            os.getcwd(),
            timeout=10,
            cancel_requested=lambda: True,
            on_progress=progress.append,
        )

        self.assertTrue(result.cancelled)
        self.assertEqual(progress, [])

    def test_timeout_terminates_process_and_reports_error(self) -> None:
        started = time.monotonic()
        result = stream_git_hashes(
            [sys.executable, "-c", "__import__('time').sleep(5)"],
            os.getcwd(),
            timeout=0.1,
        )

        self.assertFalse(result.success)
        self.assertFalse(result.cancelled)
        self.assertIn("超时", result.error)
        self.assertLess(time.monotonic() - started, 2)


if __name__ == "__main__":
    unittest.main()
