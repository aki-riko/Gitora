# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.git_service import GitService
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


class GitErrorMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def service_for(self, repo: Path) -> GitService:
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        return service

    def test_common_git_errors_are_actionable_and_chinese(self) -> None:
        cases = (
            (
                "fatal: nothing to commit, working tree clean",
                "暂存区为空，请先暂存文件再提交。",
            ),
            (
                "Author identity unknown\nPlease tell me who you are.",
                "请先配置 Git 用户信息（用户名和邮箱）。",
            ),
            (
                "fatal: not a git repository (or any of the parent directories): .git",
                "当前路径不是有效的 Git 仓库，请先打开或初始化仓库。",
            ),
            (
                "error: Your local changes to the following files would be overwritten by checkout:",
                "工作区有未提交的修改，请先提交、暂存或放弃修改后再重试。",
            ),
            (
                "error: the branch 'backup/fix-netease-pylint-before-reset-20260725' is not fully merged\n"
                "hint: If you are sure you want to delete it, run 'git branch -D backup/fix-netease-pylint-before-reset-20260725'",
                "该分支尚未完全合并，删除可能会丢失未合并的提交；如确认不再需要，请选择强制删除。",
            ),
            (
                "Automatic merge failed; fix conflicts and then commit the result.",
                "当前存在未解决的合并冲突，请先解决冲突后再继续。",
            ),
            (
                "! [rejected] main -> main (non-fast-forward)\nhint: Updates were rejected",
                "推送被拒绝：远程有本地没有的提交，请先拉取并合并后再推送。",
            ),
            (
                "fatal: The current branch main has no upstream branch.",
                "当前分支未设置上游，请先设置跟踪分支后再同步。",
            ),
            (
                "You asked to pull from the remote 'origin', but did not specify\n"
                "a branch. Because this is not the default configured remote for\n"
                "your current branch, you must specify a branch on the command line.",
                "当前分支没有配置从所选远程拉取哪个分支。请使用“拉取 → 指定拉取”同时选择远程和分支，或先为当前分支设置上游。",
            ),
            (
                "fatal: Authentication failed for 'https://example.invalid/repo.git/'",
                "远程认证失败，请检查账号、访问令牌或 SSH 密钥配置。",
            ),
            (
                "ssh: Could not resolve hostname example.invalid: Name or service not known",
                "无法连接远程仓库，请检查网络和远程地址。",
            ),
            (
                "error: pathspec 'missing' did not match any file(s) known to git",
                "找不到指定的分支、标签或文件，请检查名称是否正确。",
            ),
            (
                "fatal: src refspec main does not match any",
                "找不到要推送的本地分支或提交，请先确认当前分支和提交状态。",
            ),
            (
                "fatal: tag 'v1.0.0' already exists",
                "该标签已存在，请换一个标签名称。",
            ),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(GitService._friendly_git_error(raw, "未知错误"), expected)

    def test_duplicate_branch_uses_the_requested_name(self) -> None:
        raw = "fatal: a branch named 'codex/cherry-pick-85d001f' already exists"

        message = GitService._friendly_git_error(
            raw, "创建分支失败", branch_name="codex/cherry-pick-85d001f"
        )

        self.assertEqual(
            message,
            "分支“codex/cherry-pick-85d001f”已存在，请换一个名称，或直接使用已有分支。",
        )

    def test_unknown_git_error_is_preserved_for_diagnosis(self) -> None:
        raw = "fatal: a future Git error that Gitora does not recognize"

        self.assertEqual(GitService._friendly_git_error(raw, "未知错误"), raw)

    def test_reference_names_containing_conflict_are_not_merge_conflicts(self) -> None:
        cases = (
            (
                "error: pathspec 'conflict' did not match any file(s) known to git",
                "找不到指定的分支、标签或文件，请检查名称是否正确。",
            ),
            (
                "error: src refspec conflict does not match any",
                "找不到要推送的本地分支或提交，请先确认当前分支和提交状态。",
            ),
        )
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(GitService._friendly_git_error(raw, "未知错误"), expected)

    def test_real_git_tag_remote_and_pathspec_errors_are_rewritten(self) -> None:
        repo = init_repo(self.root / "real-errors")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        self.assertTrue(service.create_tag("v1.0.0")[0])
        ok, tag_message = service.create_tag("v1.0.0")
        self.assertFalse(ok)
        self.assertEqual(tag_message, "该标签已存在，请换一个标签名称。")

        ok, branch_message = service.checkout_branch("missing-branch")
        self.assertFalse(ok)
        self.assertEqual(
            branch_message,
            "找不到指定的分支、标签或文件，请检查名称是否正确。",
        )

        remote_url = "https://example.invalid/repo.git"
        self.assertTrue(service.add_remote("origin", remote_url)[0])
        ok, remote_message = service.add_remote("origin", remote_url)
        self.assertFalse(ok)
        self.assertEqual(remote_message, "远程仓库名称已存在，请换一个名称。")

    def test_real_checkout_with_local_changes_is_rewritten(self) -> None:
        repo = init_repo(self.root / "local-changes")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        run_git(repo, "checkout", "-b", "topic")
        write_file(repo, "tracked.txt", "topic\n")
        commit_all(repo, "topic")
        run_git(repo, "checkout", "master")
        write_file(repo, "tracked.txt", "uncommitted\n")
        service = self.service_for(repo)

        ok, message = service.checkout_branch("topic")

        self.assertFalse(ok)
        self.assertEqual(
            message,
            "工作区有未提交的修改，请先提交、暂存或放弃修改后再重试。",
        )

    def test_real_unmerged_branch_delete_is_rewritten(self) -> None:
        repo = init_repo(self.root / "unmerged-branch")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        run_git(repo, "checkout", "-b", "feature")
        write_file(repo, "feature.txt", "feature\n")
        commit_all(repo, "feature")
        run_git(repo, "checkout", "master")
        service = self.service_for(repo)

        ok, message = service.delete_branch("feature")

        self.assertFalse(ok)
        self.assertEqual(
            message,
            "该分支尚未完全合并，删除可能会丢失未合并的提交；如确认不再需要，请选择强制删除。",
        )


if __name__ == "__main__":
    unittest.main()
