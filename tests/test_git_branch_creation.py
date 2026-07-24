# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.git_service import GitService
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


class GitBranchCreationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def service_for(self, repo: Path) -> GitService:
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        return service

    def test_create_from_commit_without_checkout_preserves_workspace(self) -> None:
        repo = init_repo(self.root / "repo-from-commit")
        write_file(repo, "tracked.txt", "base\n")
        base_commit = commit_all(repo, "base")
        write_file(repo, "tracked.txt", "latest\n")
        commit_all(repo, "latest")
        write_file(repo, "tracked.txt", "uncommitted\n")
        service = self.service_for(repo)

        before_diff = run_git(repo, "diff").stdout
        ok, msg = service.create_branch(
            "from-base", checkout=False, start_point=base_commit
        )

        self.assertTrue(ok, msg)
        self.assertEqual(
            run_git(repo, "rev-parse", "refs/heads/from-base").stdout.strip(),
            base_commit,
        )
        self.assertEqual(
            run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            "master",
        )
        self.assertEqual(run_git(repo, "diff").stdout, before_diff)
        self.assertEqual(
            (repo / "tracked.txt").read_text(encoding="utf-8"),
            "uncommitted\n",
        )

    def test_create_rejects_unknown_start_point(self) -> None:
        repo = init_repo(self.root / "repo-invalid-start")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        ok, msg = service.create_branch(
            "topic", checkout=False, start_point="missing-commit"
        )

        self.assertFalse(ok)
        self.assertEqual(
            msg,
            "找不到指定的提交或引用，请检查哈希、分支或标签名称。",
        )
        self.assertNotIn("fatal:", msg.lower())
        self.assertEqual(run_git(repo, "branch", "--list", "topic").stdout, "")

    def test_duplicate_branch_returns_actionable_chinese_message(self) -> None:
        repo = init_repo(self.root / "repo-duplicate-branch")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)
        branch = "codex/cherry-pick-85d001f"
        first_ok, first_msg = service.create_branch(branch, checkout=False)
        self.assertTrue(first_ok, first_msg)

        ok, msg = service.create_branch(branch, checkout=False)

        self.assertFalse(ok)
        self.assertEqual(
            msg,
            f"分支“{branch}”已存在，请换一个名称，或直接使用已有分支。",
        )
        self.assertNotIn("fatal:", msg)

    def test_create_preserves_unborn_head_checkout_behavior(self) -> None:
        repo = init_repo(self.root / "empty-repo")
        service = self.service_for(repo)

        ok, msg = service.create_branch("topic", checkout=True)

        self.assertTrue(ok, msg)
        self.assertEqual(
            run_git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip(),
            "topic",
        )


if __name__ == "__main__":
    unittest.main()
