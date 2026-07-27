# coding: utf-8
"""合并冲突解决后必须能从冲突页真正完成合并。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.git_service import GitService
from app_qml.backend.git_bridge import GitBridge
from git_test_utils import commit_all, init_repo, run_git, write_file


class MergeContinueTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_resolved_real_merge_can_be_completed_without_editor(self) -> None:
        repo = init_repo(self.root / "merge-continue")
        write_file(repo, "conflict.txt", "base\n")
        commit_all(repo, "base")
        run_git(repo, "checkout", "-b", "incoming")
        write_file(repo, "conflict.txt", "incoming\n")
        incoming = commit_all(repo, "incoming")
        run_git(repo, "checkout", "master")
        write_file(repo, "conflict.txt", "local\n")
        local = commit_all(repo, "local")
        merge = run_git(repo, "merge", "incoming", check=False)
        self.assertNotEqual(merge.returncode, 0, merge.stdout + merge.stderr)

        write_file(repo, "conflict.txt", "resolved\n")
        run_git(repo, "add", "conflict.txt")
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        self.assertEqual(service.get_operation_state(), "merge")
        self.assertEqual(service.get_conflicts(), [])

        ok, message = service.continue_merge()

        self.assertTrue(ok, message)
        self.assertEqual(message, "合并已完成")
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual(
            run_git(repo, "rev-list", "--parents", "-n", "1", "HEAD")
            .stdout.strip()
            .split()[1:],
            [local, incoming],
        )
        self.assertEqual(
            (repo / "conflict.txt").read_text(encoding="utf-8"), "resolved\n"
        )

    def test_bridge_and_conflict_view_expose_merge_continue(self) -> None:
        self.assertTrue(callable(getattr(GitBridge, "continueMerge", None)))
        source = (
            Path(__file__).resolve().parents[1]
            / "app_qml"
            / "qml"
            / "views"
            / "ConflictView.qml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'if (root.operation === "merge") root._op(GitBridge.continueMerge())',
            source,
        )
        self.assertIn('visible: root.operation === "merge" ||', source)
        self.assertIn("冲突已解决，请点击继续完成", source)


if __name__ == "__main__":
    unittest.main()
