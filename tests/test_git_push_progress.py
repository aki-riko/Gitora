# coding: utf-8
from __future__ import annotations

import os
import sys
import time
import unittest

from app.common.git_push_progress import (
    GitPushProgressParser,
    _push_child_env,
    run_git_push_with_progress,
)


REAL_GIT_PUSH_STDERR = """\
Enumerating objects: 4, done.
Counting objects:  25% (1/4)
Counting objects:  50% (2/4)
Counting objects:  75% (3/4)
Counting objects: 100% (4/4), done.
Delta compression using up to 28 threads
Compressing objects:  33% (1/3)
Compressing objects:  66% (2/3)
Compressing objects: 100% (3/3), done.
Writing objects:  33% (1/3)
Writing objects:  66% (2/3)
Writing objects: 100% (3/3), 2.27 KiB | 465.00 KiB/s, done.
Total 3 (delta 0), reused 0 (delta 0), pack-reused 0 (from 0)
"""


class GitPushProgressParserTest(unittest.TestCase):
    def test_real_git_output_maps_to_monotonic_visible_progress(self) -> None:
        parser = GitPushProgressParser()
        updates = [
            update
            for line in REAL_GIT_PUSH_STDERR.splitlines()
            if (update := parser.feed(line)) is not None
        ]

        percents = [update.percent for update in updates]
        messages = [update.message for update in updates]
        self.assertEqual(percents, sorted(percents))
        self.assertGreaterEqual(percents[-1], 95)
        self.assertTrue(any("正在计数对象 2/4" in item for item in messages))
        self.assertTrue(any("正在压缩对象 2/3" in item for item in messages))
        self.assertTrue(any("正在写入对象 3/3" in item for item in messages))
        self.assertTrue(any("465.00 KiB/s" in item for item in messages))

    def test_remote_delta_and_up_to_date_never_reach_completion_early(self) -> None:
        parser = GitPushProgressParser()
        resolving = parser.feed("remote: Resolving deltas: 100% (8/8), done.")
        current = parser.feed("Everything up-to-date")

        self.assertIsNotNone(resolving)
        self.assertEqual(resolving.percent, 99)
        self.assertIn("远端正在解析增量", resolving.message)
        self.assertIsNotNone(current)
        self.assertEqual(current.percent, 99)


class GitPushTimeoutCleanupTest(unittest.TestCase):
    """超时后的清理必须有界。

    回归：只杀顶层 git.exe 时，git 派生的 ssh / git-remote-https / 凭据助手会继续
    持有 stdout/stderr 管道写端，读取端永远等不到 EOF。旧实现会在
    ``await asyncio.gather(stdout_reader, stderr_reader)`` 上永久挂住，
    导致界面进度条停住、operationBusy 恒为 true、日志再无输出。
    """

    def test_timeout_with_pipe_holding_descendant_still_returns(self) -> None:
        # 父进程挂住，同时留下一个继承 stdio 的孙进程 —— 等价 git.exe 派生 ssh。
        script = (
            "import subprocess, sys, time;"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']);"
            "time.sleep(30)"
        )
        timeout = 2
        started = time.monotonic()
        result = run_git_push_with_progress(
            [sys.executable, "-c", script],
            os.getcwd(),
            timeout,
            lambda _percent, _message: None,
        )
        elapsed = time.monotonic() - started

        self.assertFalse(result.success)
        self.assertIn("超时", result.stderr)
        # 超时 + 清理宽限期之内必须返回，不能被管道持有者永久钉死。
        self.assertLess(elapsed, timeout + 20)

    def test_child_env_disables_invisible_terminal_prompts(self) -> None:
        env = _push_child_env()

        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GCM_INTERACTIVE"], "never")
        self.assertIn("BatchMode=yes", env.get("GIT_SSH_COMMAND", ""))
        # 非交互取凭据的路径（GIT_ASKPASS 等）必须保持原样，不能被这次修复误伤。
        self.assertEqual(
            env.get("GIT_ASKPASS"), os.environ.get("GIT_ASKPASS")
        )


if __name__ == "__main__":
    unittest.main()
