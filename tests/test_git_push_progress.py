# coding: utf-8
from __future__ import annotations

import unittest

from app.common.git_push_progress import GitPushProgressParser


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


if __name__ == "__main__":
    unittest.main()
