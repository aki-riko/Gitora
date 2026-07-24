# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.common.git_service import GitService
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ERROR_CASES = (
    ("fatal: nothing to commit, working tree clean", "暂存区为空，请先暂存文件再提交。"),
    ("Author identity unknown\nPlease tell me who you are.", "请先配置 Git 用户信息（用户名和邮箱）。"),
    ("fatal: not a git repository (or any of the parent directories): .git", "当前路径不是有效的 Git 仓库，请先打开或初始化仓库。"),
    ("fatal: your current branch 'master' does not have any commits yet", "当前仓库还没有提交，请先完成首次提交。"),
    ("error: Your local changes would be overwritten by checkout", "工作区有未提交的修改，请先提交、暂存或放弃修改后再重试。"),
    ("error: untracked working tree files would be overwritten by checkout", "未跟踪文件会被本次操作覆盖，请先移动、删除或暂存这些文件。"),
    ("error: the branch 'topic' is not fully merged", "该分支尚未完全合并，删除可能会丢失未合并的提交；如确认不再需要，请选择强制删除。"),
    ("Automatic merge failed; fix conflicts and then commit the result.", "当前存在未解决的合并冲突，请先解决冲突后再继续。"),
    ("fatal: It seems that there is already a rebase-merge directory", "当前已有未完成的变基操作，请先继续、跳过或中止该操作。"),
    ("fatal: no rebase in progress", "当前没有可继续或中止的 Git 操作。"),
    ("fatal: No stash entries found.", "当前没有可用的 stash 记录。"),
    ("Aborting commit due to empty commit message.", "提交信息不能为空，请填写后重试。"),
    ("fatal: You are not currently on a branch.", "当前处于分离头指针状态，请先切换或创建分支后再继续。"),
    ("fatal: detected dubious ownership in repository at 'D:/repo'", "Git 因仓库目录所有权异常拒绝操作，请确认该目录可信后再标记为安全目录。"),
    ("remote: error: protected branch hook declined\n! [remote rejected] main -> main", "远程仓库规则拒绝了本次更新，请检查受保护分支、提交规范或服务器钩子要求。"),
    ("fatal: 'origin' does not appear to be a git repository", "远程仓库不存在或当前账号无权访问，请检查远程地址和权限。"),
    ("! [rejected] main -> main (non-fast-forward)\nhint: Updates were rejected", "推送被拒绝：远程有本地没有的提交，请先拉取并合并后再推送。"),
    ("fatal: The current branch main has no upstream branch.", "当前分支未设置上游，请先设置跟踪分支后再同步。"),
    ("You asked to pull from the remote 'origin', but did not specify a branch. You must specify a branch on the command line.", "当前分支没有配置从所选远程拉取哪个分支。请使用“拉取 → 指定拉取”同时选择远程和分支，或先为当前分支设置上游。"),
    ("fatal: Authentication failed for 'https://example.invalid/repo.git/'", "远程认证失败，请检查账号、访问令牌、SSH 密钥及仓库权限。"),
    ("fatal: unable to access: SSL certificate problem: unable to get local issuer certificate", "远程服务器证书校验失败，请检查系统时间、证书链或代理设置。"),
    ("ssh: Could not resolve hostname example.invalid: Name or service not known", "无法连接远程仓库，请检查网络、代理和远程地址。"),
    ("fetch-pack: unexpected disconnect while reading sideband packet", "与远程仓库的连接中途断开，请检查网络稳定性后重试。"),
    ("fatal: Not possible to fast-forward, aborting.", "本地与远程分支已分叉，请选择合并或变基方式后再拉取。"),
    ("fatal: couldn't find remote ref missing", "远程仓库中找不到指定的分支或标签，请刷新远程信息后重新选择。"),
    ("error: No such remote: 'backup'", "找不到指定的远程仓库，请刷新远程列表或重新配置远程。"),
    ("error: pathspec 'missing' did not match any file(s) known to git", "找不到指定的分支、标签或文件，请检查名称是否正确。"),
    ("fatal: src refspec main does not match any", "找不到要推送的本地分支或提交，请先确认当前分支和提交状态。"),
    ("fatal: invalid object name 'missing'", "指定内容不是有效的提交或引用，请重新选择。"),
    ("fatal: 'topic' is already checked out at 'D:/other'", "该分支已在其他工作树中检出，不能重复检出。"),
    ("fatal: tag 'v1.0.0' already exists", "该标签已存在，请换一个标签名称。"),
    ("fatal: a branch named 'topic' already exists", "同名分支已存在，请换一个名称或直接使用已有分支。"),
    ("error: Cannot delete branch 'main' checked out at 'D:/repo'", "不能删除当前正在使用的分支，请先切换到其他分支。"),
    ("fatal: refusing to merge unrelated histories", "两个仓库历史没有共同起点，不能直接合并；请确认后再选择允许合并无关历史。"),
    ("error: cannot lock ref 'refs/heads/main': is at abc but expected def", "分支或标签已被其他 Git 操作更新，请刷新仓库状态后重试。"),
    ("fatal: invalid refspec 'bad ref'", "分支、标签或远程引用名称不合法，请修改名称后重试。"),
    ("fatal: unable to write file: No space left on device", "磁盘空间不足，无法完成 Git 操作，请清理空间后重试。"),
    ("fatal: cannot create file: Read-only file system", "仓库所在位置为只读，无法写入，请检查磁盘或目录权限。"),
    ("error: unable to create file: Filename too long", "文件路径过长，Git 无法处理，请缩短仓库路径或文件名。"),
    ("fatal: cannot open '.git/index': Permission denied", "Git 无权读写相关文件，请检查仓库目录和文件权限。"),
    ("fatal: destination path 'repo' already exists and is not an empty directory.", "目标目录已存在且不为空，请选择空目录或新的保存位置。"),
    ("fatal: could not create work tree dir 'repo': Access is denied", "Git 无权读写相关文件，请检查仓库目录和文件权限。"),
    ("fatal: cannot remove a locked working tree", "该工作树已锁定，请先确认没有任务使用它，再解除锁定后重试。"),
    ("git: 'lfs' is not a git command. See 'git --help'.", "当前系统未安装 Git LFS，请先安装并初始化 Git LFS。"),
    ("fatal: No url found for submodule path 'vendor/lib' in .gitmodules", "子模块配置不完整，请检查 .gitmodules 中的路径和地址。"),
    ("fatal: bad config line 3 in file .git/config", "Git 配置文件包含无效内容，请检查对应配置项。"),
    ("fatal: 'D:/repo' is already registered worktree", "工作树记录与磁盘状态不一致，请先清理或修复 worktree 记录。"),
)


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
        for raw, expected in ERROR_CASES:
            with self.subTest(raw=raw):
                message = GitService._friendly_git_error(raw, "未知错误")
                self.assertEqual(message, expected)
                self.assertNotRegex(message, r"(?i)\b(?:fatal|error|hint):")

    def test_duplicate_branch_uses_the_requested_name(self) -> None:
        raw = "fatal: a branch named 'codex/cherry-pick-85d001f' already exists"

        message = GitService._friendly_git_error(
            raw, "创建分支失败", branch_name="codex/cherry-pick-85d001f"
        )

        self.assertEqual(
            message,
            "分支“codex/cherry-pick-85d001f”已存在，请换一个名称，或直接使用已有分支。",
        )

    def test_unknown_git_error_uses_chinese_fallback_for_users(self) -> None:
        secret = "ghp_abcdefghijklmnopqrstuvwxyz123456"
        raw = (
            "fatal: a future Git error from "
            f"https://user:password@example.invalid/repo.git?token={secret}"
        )

        with patch("app.common.git_service.logger.warning") as warning:
            message = GitService._friendly_git_error(raw, "切换分支失败")

        self.assertEqual(
            message,
            "切换分支失败。请检查仓库状态后重试；技术详情已记录到日志。",
        )
        self.assertNotIn(raw, message)
        self.assertNotIn("fatal:", message.lower())
        logged = warning.call_args.args[0]
        self.assertNotIn("user:password", logged)
        self.assertNotIn(secret, logged)
        self.assertIn("https://***@example.invalid/repo.git?token=***", logged)

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
