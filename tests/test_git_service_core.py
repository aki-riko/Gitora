# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.common.git_service import FileStatus, GitService

from git_test_utils import (
    clone_repo,
    commit_all,
    init_bare_repo,
    init_repo,
    run_git,
    write_file,
)


class GitServiceCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def service_for(self, repo: Path) -> GitService:
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        return service

    def wait_operation(self, service: GitService, starter, timeout_ms: int = 10000) -> tuple[bool, str]:
        app = QCoreApplication.instance() or QCoreApplication([])
        loop = QEventLoop()
        result: dict[str, object] = {}

        def on_finished(ok: bool, msg: str) -> None:
            result["ok"] = ok
            result["msg"] = msg
            loop.quit()

        service.operationFinished.connect(on_finished)
        QTimer.singleShot(timeout_ms, loop.quit)
        starter()
        loop.exec()
        service.operationFinished.disconnect(on_finished)
        self.assertIn("ok", result, "Git operation did not finish before timeout")
        return bool(result["ok"]), str(result["msg"])

    def test_clone_uses_target_parent_without_existing_repo_path(self) -> None:
        service = GitService()
        self.assertIsNone(service.repo_path)
        target = self.root / "cloned"
        seen: dict[str, object] = {}

        def fake_run_git_async(args, callback, timeout=None, cwd=None):
            seen["args"] = args
            seen["timeout"] = timeout
            seen["cwd"] = cwd
            callback(True, "", "")

        service._run_git_async = fake_run_git_async  # type: ignore[method-assign]

        ok, msg = self.wait_operation(
            service,
            lambda: service.clone("git@example.com:Aquila/Test.git", str(target)),
        )

        self.assertTrue(ok, msg)
        self.assertEqual(seen["args"], [
            "clone",
            "git@example.com:Aquila/Test.git",
            str(target),
            "--progress",
        ])
        self.assertEqual(seen["timeout"], 300)
        self.assertEqual(seen["cwd"], str(self.root))

    def make_rebase_conflict_repo(self, name: str) -> tuple[Path, GitService]:
        repo = init_repo(self.root / name)
        write_file(repo, "conflict.txt", "base\n")
        commit_all(repo, "base")
        run_git(repo, "checkout", "-b", "topic")
        write_file(repo, "conflict.txt", "topic\n")
        commit_all(repo, "topic")
        run_git(repo, "checkout", "master")
        write_file(repo, "conflict.txt", "master\n")
        commit_all(repo, "master")
        run_git(repo, "checkout", "topic")
        return repo, self.service_for(repo)

    def make_cherry_pick_conflict_repo(self, name: str) -> tuple[Path, GitService, str]:
        repo = init_repo(self.root / name)
        write_file(repo, "conflict.txt", "base\n")
        commit_all(repo, "base")
        run_git(repo, "checkout", "-b", "source")
        write_file(repo, "conflict.txt", "picked\n")
        source_commit = commit_all(repo, "source change")
        run_git(repo, "checkout", "master")
        write_file(repo, "conflict.txt", "master\n")
        commit_all(repo, "master change")
        return repo, self.service_for(repo), source_commit

    def make_revert_conflict_repo(self, name: str) -> tuple[Path, GitService, str]:
        repo = init_repo(self.root / name)
        write_file(repo, "conflict.txt", "base\n")
        commit_all(repo, "base")
        write_file(repo, "conflict.txt", "target\n")
        target_commit = commit_all(repo, "target change")
        write_file(repo, "conflict.txt", "current\n")
        commit_all(repo, "current change")
        return repo, self.service_for(repo), target_commit

    def test_stage_commit_and_hard_reset_use_real_repo(self) -> None:
        repo = init_repo(self.root / "repo")
        service = self.service_for(repo)

        write_file(repo, "tracked.txt", "one\n")
        changes = service.get_status()
        self.assertEqual([(c.path, c.status, c.staged) for c in changes], [
            ("tracked.txt", FileStatus.UNTRACKED, False),
        ])

        self.assertTrue(service.stage_all())
        staged = service.get_status()
        self.assertEqual([(c.path, c.status, c.staged) for c in staged], [
            ("tracked.txt", FileStatus.ADDED, True),
        ])

        ok, msg = service.commit("initial")
        self.assertTrue(ok, msg)
        first_commit = run_git(repo, "rev-parse", "HEAD").stdout.strip()

        write_file(repo, "tracked.txt", "two\n")
        self.assertTrue(service.stage_all())
        ok, msg = service.commit("second")
        self.assertTrue(ok, msg)

        ok, msg = service.reset_to_commit(first_commit, "hard")
        self.assertTrue(ok, msg)
        self.assertEqual((repo / "tracked.txt").read_text(encoding="utf-8"), "one\n")
        self.assertEqual(service.get_status(), [])

    def test_is_head_pushed_tracks_upstream_with_real_remote(self) -> None:
        remote = init_bare_repo(self.root / "remote.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "README.md", "seed\n")
        commit_all(seed, "seed")
        run_git(seed, "remote", "add", "origin", str(remote))
        run_git(seed, "push", "-u", "origin", "master")

        clone = clone_repo(remote, self.root / "clone")
        service = self.service_for(clone)
        self.assertTrue(service.is_head_pushed())

        write_file(clone, "local.txt", "local\n")
        commit_all(clone, "local")
        self.assertFalse(service.is_head_pushed())

        run_git(clone, "push")
        self.assertTrue(service.is_head_pushed())

    def test_force_reset_to_upstream_discards_local_commit_and_tracked_change(self) -> None:
        remote = init_bare_repo(self.root / "remote.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "tracked.txt", "base\n")
        commit_all(seed, "base")
        run_git(seed, "remote", "add", "origin", str(remote))
        run_git(seed, "push", "-u", "origin", "master")

        clone = clone_repo(remote, self.root / "clone")
        service = self.service_for(clone)
        write_file(clone, "local.txt", "local commit\n")
        local_commit = commit_all(clone, "local commit")
        write_file(clone, "tracked.txt", "local dirty\n")

        write_file(seed, "tracked.txt", "remote wins\n")
        remote_commit = commit_all(seed, "remote wins")
        run_git(seed, "push")

        ok, msg = service.force_reset_to_upstream_sync()
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(clone, "rev-parse", "HEAD").stdout.strip(), remote_commit)
        self.assertEqual((clone / "tracked.txt").read_text(encoding="utf-8"), "remote wins\n")
        self.assertEqual(service.get_status(), [])
        contains_local = run_git(
            clone, "merge-base", "--is-ancestor", local_commit, "HEAD", check=False)
        self.assertNotEqual(contains_local.returncode, 0)

    def test_force_reset_to_upstream_requires_configured_upstream(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        ok, msg = service.force_reset_to_upstream_sync()
        self.assertFalse(ok)
        self.assertIn("上游", msg)

    def test_fetch_pull_and_push_accept_explicit_remote_and_branch(self) -> None:
        remote = init_bare_repo(self.root / "remote.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "tracked.txt", "base\n")
        commit_all(seed, "base")
        run_git(seed, "remote", "add", "upstream", str(remote))
        run_git(seed, "push", "-u", "upstream", "master")

        clone = clone_repo(remote, self.root / "clone")
        run_git(clone, "remote", "rename", "origin", "upstream")
        service = self.service_for(clone)

        write_file(seed, "tracked.txt", "remote update\n")
        commit_all(seed, "remote update")
        run_git(seed, "push", "upstream", "master")

        ok, msg = self.wait_operation(service, lambda: service.fetch("upstream"))
        self.assertTrue(ok, msg)
        fetched = run_git(clone, "rev-parse", "refs/remotes/upstream/master").stdout.strip()
        self.assertEqual(
            fetched,
            run_git(seed, "rev-parse", "HEAD").stdout.strip(),
        )

        ok, msg = self.wait_operation(service, lambda: service.pull("upstream", "master"))
        self.assertTrue(ok, msg)
        self.assertEqual((clone / "tracked.txt").read_text(encoding="utf-8"), "remote update\n")

        ok, msg = service.create_branch("feature", checkout=True)
        self.assertTrue(ok, msg)
        write_file(clone, "feature.txt", "feature\n")
        commit_all(clone, "feature")
        ok, msg = self.wait_operation(service, lambda: service.push("upstream", "feature"))
        self.assertTrue(ok, msg)
        pushed = run_git(remote, "rev-parse", "refs/heads/feature").stdout.strip()
        self.assertEqual(pushed, run_git(clone, "rev-parse", "feature").stdout.strip())
        upstream = run_git(
            clone, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
        self.assertEqual(upstream, "upstream/feature")

    def test_unmerged_branch_requires_force_delete(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "base.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        ok, msg = service.create_branch("feature", checkout=True)
        self.assertTrue(ok, msg)
        write_file(repo, "feature.txt", "feature\n")
        commit_all(repo, "feature")
        ok, msg = service.checkout_branch("master")
        self.assertTrue(ok, msg)

        ok, msg = service.delete_branch("feature", force=False)
        self.assertFalse(ok, msg)
        ok, msg = service.delete_branch("feature", force=True)
        self.assertTrue(ok, msg)
        branches = run_git(repo, "branch", "--list", "feature").stdout.strip()
        self.assertEqual(branches, "")

    def test_rename_branch_set_upstream_and_rename_remote_use_real_repo(self) -> None:
        remote = init_bare_repo(self.root / "remote.git")
        repo = init_repo(self.root / "repo")
        write_file(repo, "base.txt", "base\n")
        commit_all(repo, "base")
        run_git(repo, "remote", "add", "origin", str(remote))
        run_git(repo, "push", "-u", "origin", "master")
        service = self.service_for(repo)

        ok, msg = service.create_branch("feature", checkout=True)
        self.assertTrue(ok, msg)
        write_file(repo, "feature.txt", "feature\n")
        commit_all(repo, "feature")
        run_git(repo, "push", "origin", "feature")

        ok, msg = service.rename_branch("feature", "topic")
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "topic")
        self.assertEqual(run_git(repo, "branch", "--list", "feature").stdout.strip(), "")
        self.assertIn("topic", run_git(repo, "branch", "--list", "topic").stdout)

        ok, msg = service.set_upstream("topic", "origin", "feature")
        self.assertTrue(ok, msg)
        upstream = run_git(
            repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
        self.assertEqual(upstream, "origin/feature")

        ok, msg = service.rename_remote("origin", "upstream")
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_remotes(), ["upstream"])

    def test_checkout_remote_branch_creates_tracking_local_branch(self) -> None:
        remote = init_bare_repo(self.root / "remote.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "base.txt", "base\n")
        commit_all(seed, "base")
        run_git(seed, "checkout", "-b", "feature")
        write_file(seed, "feature.txt", "feature\n")
        feature_commit = commit_all(seed, "feature")
        run_git(seed, "remote", "add", "origin", str(remote))
        run_git(seed, "push", "-u", "origin", "master", "feature")

        clone = clone_repo(remote, self.root / "clone")
        service = self.service_for(clone)
        ok, msg = service.checkout_remote_branch("origin/feature", "local-feature")
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(clone, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "local-feature")
        self.assertEqual(run_git(clone, "rev-parse", "HEAD").stdout.strip(), feature_commit)
        upstream = run_git(
            clone, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
        self.assertEqual(upstream, "origin/feature")

    def test_rebase_continue_skip_and_abort_use_real_conflicts(self) -> None:
        repo, service = self.make_rebase_conflict_repo("rebase-continue")
        ok, msg = service.rebase_onto("master")
        self.assertFalse(ok, msg)
        self.assertEqual(service.get_operation_state(), "rebase")
        self.assertTrue(service.get_conflicts())
        write_file(repo, "conflict.txt", "resolved\n")
        run_git(repo, "add", "conflict.txt")
        ok, msg = service.continue_rebase()
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual((repo / "conflict.txt").read_text(encoding="utf-8"), "resolved\n")

        repo, service = self.make_rebase_conflict_repo("rebase-skip")
        master_commit = run_git(repo, "rev-parse", "master").stdout.strip()
        ok, msg = service.rebase_onto("master")
        self.assertFalse(ok, msg)
        self.assertEqual(service.get_operation_state(), "rebase")
        ok, msg = service.skip_rebase()
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual(run_git(repo, "rev-parse", "HEAD").stdout.strip(), master_commit)
        self.assertEqual((repo / "conflict.txt").read_text(encoding="utf-8"), "master\n")

        repo, service = self.make_rebase_conflict_repo("rebase-abort")
        topic_commit = run_git(repo, "rev-parse", "topic").stdout.strip()
        ok, msg = service.rebase_onto("master")
        self.assertFalse(ok, msg)
        self.assertEqual(service.get_operation_state(), "rebase")
        ok, msg = service.abort_rebase()
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual(run_git(repo, "rev-parse", "HEAD").stdout.strip(), topic_commit)
        self.assertEqual((repo / "conflict.txt").read_text(encoding="utf-8"), "topic\n")

    def test_cherry_pick_continue_and_abort_use_real_conflicts(self) -> None:
        repo, service, source_commit = self.make_cherry_pick_conflict_repo("cherry-continue")
        ok, msg = service.cherry_pick(source_commit)
        self.assertFalse(ok, msg)
        self.assertEqual(service.get_operation_state(), "cherry-pick")
        self.assertTrue(service.get_conflicts())
        write_file(repo, "conflict.txt", "picked\n")
        run_git(repo, "add", "conflict.txt")
        ok, msg = service.continue_cherry_pick()
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual((repo / "conflict.txt").read_text(encoding="utf-8"), "picked\n")

        repo, service, source_commit = self.make_cherry_pick_conflict_repo("cherry-abort")
        master_commit = run_git(repo, "rev-parse", "HEAD").stdout.strip()
        ok, msg = service.cherry_pick(source_commit)
        self.assertFalse(ok, msg)
        self.assertEqual(service.get_operation_state(), "cherry-pick")
        ok, msg = service.abort_cherry_pick()
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual(run_git(repo, "rev-parse", "HEAD").stdout.strip(), master_commit)
        self.assertEqual((repo / "conflict.txt").read_text(encoding="utf-8"), "master\n")

    def test_revert_continue_and_abort_use_real_conflicts(self) -> None:
        repo, service, target_commit = self.make_revert_conflict_repo("revert-continue")
        ok, msg = service.revert_commit(target_commit)
        self.assertFalse(ok, msg)
        self.assertEqual(service.get_operation_state(), "revert")
        self.assertTrue(service.get_conflicts())
        write_file(repo, "conflict.txt", "base\n")
        run_git(repo, "add", "conflict.txt")
        ok, msg = service.continue_revert()
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual((repo / "conflict.txt").read_text(encoding="utf-8"), "base\n")

        repo, service, target_commit = self.make_revert_conflict_repo("revert-abort")
        head_before = run_git(repo, "rev-parse", "HEAD").stdout.strip()
        ok, msg = service.revert_commit(target_commit)
        self.assertFalse(ok, msg)
        self.assertEqual(service.get_operation_state(), "revert")
        ok, msg = service.abort_revert()
        self.assertTrue(ok, msg)
        self.assertEqual(service.get_operation_state(), "")
        self.assertEqual(run_git(repo, "rev-parse", "HEAD").stdout.strip(), head_before)
        self.assertEqual((repo / "conflict.txt").read_text(encoding="utf-8"), "current\n")

    def test_stash_apply_pop_drop_and_clear_use_real_repo(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        write_file(repo, "tracked.txt", "stashed\n")
        ok, msg = service.stash_save("work in progress")
        self.assertTrue(ok, msg)
        self.assertEqual(len(service.stash_list()), 1)
        self.assertEqual((repo / "tracked.txt").read_text(encoding="utf-8"), "base\n")

        stash_id = service.stash_list()[0][0]
        ok, msg = service.stash_apply(stash_id)
        self.assertTrue(ok, msg)
        self.assertEqual((repo / "tracked.txt").read_text(encoding="utf-8"), "stashed\n")
        run_git(repo, "reset", "--hard", "HEAD")
        self.assertEqual(len(service.stash_list()), 1)

        ok, msg = service.stash_pop(stash_id)
        self.assertTrue(ok, msg)
        self.assertEqual((repo / "tracked.txt").read_text(encoding="utf-8"), "stashed\n")
        self.assertEqual(service.stash_list(), [])

        run_git(repo, "reset", "--hard", "HEAD")
        write_file(repo, "tracked.txt", "drop me\n")
        ok, msg = service.stash_save("drop me")
        self.assertTrue(ok, msg)
        stash_id = service.stash_list()[0][0]
        ok, msg = service.stash_drop(stash_id)
        self.assertTrue(ok, msg)
        self.assertEqual(service.stash_list(), [])

        write_file(repo, "tracked.txt", "clear me\n")
        ok, msg = service.stash_save("clear me")
        self.assertTrue(ok, msg)
        ok, msg = service.stash_clear()
        self.assertTrue(ok, msg)
        self.assertEqual(service.stash_list(), [])

    def test_stash_options_and_show_use_real_repo(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        write_file(repo, "untracked.txt", "new\n")
        ok, msg = service.stash_save("with untracked", include_untracked=True)
        self.assertTrue(ok, msg)
        self.assertFalse((repo / "untracked.txt").exists())
        stash_id = service.stash_list()[0][0]
        ok, content = service.stash_show(stash_id)
        self.assertTrue(ok, content)
        self.assertIn("untracked.txt", content)
        ok, msg = service.stash_pop(stash_id)
        self.assertTrue(ok, msg)
        self.assertEqual((repo / "untracked.txt").read_text(encoding="utf-8"), "new\n")

        run_git(repo, "reset", "--hard", "HEAD")
        run_git(repo, "clean", "-fd")
        write_file(repo, "tracked.txt", "staged\n")
        run_git(repo, "add", "tracked.txt")
        write_file(repo, "tracked.txt", "unstaged\n")
        ok, msg = service.stash_save("keep index", keep_index=True)
        self.assertTrue(ok, msg)
        self.assertEqual((repo / "tracked.txt").read_text(encoding="utf-8"), "staged\n")
        cached_diff = run_git(repo, "diff", "--cached", "--", "tracked.txt").stdout
        self.assertIn("staged", cached_diff)
        self.assertEqual(run_git(repo, "diff", "--", "tracked.txt").stdout, "")

    def test_stash_branch_creates_branch_from_real_stash(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        write_file(repo, "tracked.txt", "stashed branch\n")
        ok, msg = service.stash_save("branch me")
        self.assertTrue(ok, msg)
        stash_id = service.stash_list()[0][0]

        ok, msg = service.stash_branch("from-stash", stash_id)
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "from-stash")
        self.assertEqual((repo / "tracked.txt").read_text(encoding="utf-8"), "stashed branch\n")
        self.assertEqual(service.stash_list(), [])

        ok, msg = service.stash_branch("../bad", stash_id)
        self.assertFalse(ok)
        self.assertIn("非法", msg)

    def test_tag_types_and_remote_delete_use_real_repo(self) -> None:
        remote = init_bare_repo(self.root / "remote.git")
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        run_git(repo, "remote", "add", "origin", str(remote))
        run_git(repo, "push", "-u", "origin", "master")
        service = self.service_for(repo)

        ok, msg = service.create_tag("v-light", "ignored message", annotated=False)
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(repo, "cat-file", "-t", "v-light").stdout.strip(), "commit")

        ok, msg = service.create_tag("v-ann", "release notes", annotated=True)
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(repo, "cat-file", "-t", "v-ann").stdout.strip(), "tag")

        ok, msg = service.push_tag("v-ann", "origin")
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(remote, "rev-parse", "refs/tags/v-ann^{tag}").returncode, 0)

        ok, msg = service.delete_remote_tag("v-ann", "origin")
        self.assertTrue(ok, msg)
        missing_remote_tag = run_git(remote, "rev-parse", "refs/tags/v-ann", check=False)
        self.assertNotEqual(missing_remote_tag.returncode, 0)
        self.assertEqual(run_git(repo, "rev-parse", "refs/tags/v-ann^{tag}").returncode, 0)

        ok, msg = service.delete_tag("v-light")
        self.assertTrue(ok, msg)
        self.assertEqual(run_git(repo, "tag", "--list", "v-light").stdout.strip(), "")

    def test_get_tags_at_uses_captured_repository_path(self) -> None:
        repo_a = init_repo(self.root / "repo-a")
        repo_b = init_repo(self.root / "repo-b")
        for repo, tag in ((repo_a, "tag-a"), (repo_b, "tag-b")):
            write_file(repo, "tracked.txt", tag + "\n")
            commit_all(repo, tag)
            run_git(repo, "tag", tag)

        service = self.service_for(repo_b)

        self.assertEqual([item[0] for item in service.get_tags_at(str(repo_a))], ["tag-a"])
        self.assertEqual([item[0] for item in service.get_tags()], ["tag-b"])

    def test_worktree_add_list_remove_use_real_repo(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)
        worktree_path = self.root / "repo-topic"

        ok, msg = service.add_worktree(str(worktree_path), "topic", create_branch=True)
        self.assertTrue(ok, msg)
        worktrees = service.list_worktrees()
        self.assertTrue(any(w.path.replace("\\", "/").endswith("repo-topic") and w.branch == "topic" for w in worktrees))
        self.assertTrue((worktree_path / "tracked.txt").exists())
        self.assertTrue((worktree_path / ".git").is_file())

        worktree_service = GitService()
        self.assertTrue(worktree_service.set_repo_path(str(worktree_path)))
        self.assertEqual(worktree_service.get_current_branch(), "topic")
        self.assertNotEqual(worktree_service.compute_state_fingerprint(str(worktree_path)), "")

        ok, msg = service.remove_worktree(str(worktree_path), force=False)
        self.assertTrue(ok, msg)
        self.assertFalse(worktree_path.exists())

    def test_submodule_update_and_sync_use_real_repo(self) -> None:
        sub = init_repo(self.root / "sub")
        write_file(sub, "sub.txt", "sub\n")
        commit_all(sub, "sub")

        repo = init_repo(self.root / "repo")
        write_file(repo, "root.txt", "root\n")
        commit_all(repo, "root")
        run_git(repo, "config", "protocol.file.allow", "always")
        run_git(repo, "-c", "protocol.file.allow=always", "submodule", "add", str(sub), "libs/sub")
        commit_all(repo, "add submodule")
        service = self.service_for(repo)

        modules = service.list_submodules()
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].path, "libs/sub")

        run_git(repo, "submodule", "deinit", "-f", "libs/sub")
        self.assertFalse((repo / "libs" / "sub" / "sub.txt").exists())
        ok, msg = service.submodule_update(init=True, recursive=True)
        self.assertTrue(ok, msg)
        self.assertTrue((repo / "libs" / "sub" / "sub.txt").exists())

        ok, msg = service.submodule_sync(recursive=True)
        self.assertTrue(ok, msg)

    def test_lfs_status_use_real_repo(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        service = self.service_for(repo)

        ok, msg = service.lfs_status()
        self.assertTrue(ok, msg)
        self.assertIn("Git LFS", msg)

    def test_bisect_flow_use_real_repo(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "value.txt", "0\n")
        good_commit = commit_all(repo, "value 0")
        for value in ("1", "2", "3"):
            write_file(repo, "value.txt", value + "\n")
            commit_all(repo, f"value {value}")
        service = self.service_for(repo)

        ok, msg = service.bisect_start(good_commit, "HEAD")
        self.assertTrue(ok, msg)
        self.assertTrue(service.is_bisecting())

        result_text = ""
        for _ in range(5):
            value = int((repo / "value.txt").read_text(encoding="utf-8").strip())
            ok, result_text = service.bisect_bad() if value >= 2 else service.bisect_good()
            self.assertTrue(ok, result_text)
            if "first bad commit" in result_text:
                break
        self.assertIn("first bad commit", result_text)

        ok, log_text = service.bisect_log()
        self.assertTrue(ok, log_text)
        self.assertIn("git bisect start", log_text)

        ok, msg = service.bisect_reset()
        self.assertTrue(ok, msg)
        self.assertFalse(service.is_bisecting())
        self.assertEqual(run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), "master")

    def test_parse_diff_summary_and_filter_use_real_git_output(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "one\ntwo\nthree\n")
        first_commit = commit_all(repo, "base")
        service = self.service_for(repo)

        write_file(repo, "tracked.txt", "one\nTWO\nthree\nfour\n")
        write_file(repo, "added.txt", "new\n")
        working_diff = service.get_diff("tracked.txt")
        parsed_working = GitService.parse_unified_diff(working_diff)
        self.assertEqual(len(parsed_working), 1)
        self.assertEqual(parsed_working[0].path, "tracked.txt")
        self.assertEqual(parsed_working[0].additions, 2)
        self.assertEqual(parsed_working[0].deletions, 1)
        self.assertEqual(
            [line.kind for line in parsed_working[0].hunks[0].lines],
            ["context", "deleted", "added", "context", "added"],
        )

        second_commit = commit_all(repo, "modify and add")
        commit_diff = service.get_commit_diff(second_commit)
        parsed_commit = GitService.parse_unified_diff(commit_diff)
        by_path = {item.path: item for item in parsed_commit}
        self.assertEqual(by_path["tracked.txt"].status, "modified")
        self.assertEqual(by_path["added.txt"].status, "added")
        self.assertEqual(by_path["added.txt"].additions, 1)

        filtered = GitService.filter_unified_diff(commit_diff, "tracked.txt")
        self.assertIn("diff --git a/tracked.txt b/tracked.txt", filtered)
        self.assertNotIn("added.txt", filtered)

        between = service.diff_file_between_commits("tracked.txt", first_commit, second_commit)
        parsed_between = GitService.parse_unified_diff(between)
        self.assertEqual(len(parsed_between), 1)
        self.assertEqual(parsed_between[0].path, "tracked.txt")
        self.assertIn("+four", between)

    def test_parse_diff_handles_rename_delete_and_binary_git_output(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "old-name.txt", "same\ncontent\n")
        write_file(repo, "delete-me.txt", "remove\n")
        (repo / "image.bin").write_bytes(bytes([0, 1, 2, 0, 255]))
        commit_all(repo, "base")
        service = self.service_for(repo)

        run_git(repo, "mv", "old-name.txt", "new-name.txt")
        (repo / "delete-me.txt").unlink()
        (repo / "image.bin").write_bytes(bytes([0, 1, 3, 0, 255, 4]))
        changed_commit = commit_all(repo, "rename delete binary")

        commit_diff = service.get_commit_diff(changed_commit)
        parsed = GitService.parse_unified_diff(commit_diff)
        by_path = {item.path: item for item in parsed}

        renamed = by_path["new-name.txt"]
        self.assertEqual(renamed.status, "renamed")
        self.assertEqual(renamed.old_path, "old-name.txt")
        self.assertEqual(renamed.new_path, "new-name.txt")
        self.assertEqual(renamed.additions, 0)
        self.assertEqual(renamed.deletions, 0)

        deleted = by_path["delete-me.txt"]
        self.assertEqual(deleted.status, "deleted")
        self.assertEqual(deleted.old_path, "delete-me.txt")
        self.assertEqual(deleted.new_path, "")
        self.assertEqual(deleted.additions, 0)
        self.assertEqual(deleted.deletions, 1)

        binary = by_path["image.bin"]
        self.assertEqual(binary.status, "modified")
        self.assertEqual(binary.additions, 0)
        self.assertEqual(binary.deletions, 0)
        self.assertEqual(binary.hunks, [])
        self.assertIn("Binary files", binary.raw)

        rename_filtered = GitService.filter_unified_diff(commit_diff, "old-name.txt")
        self.assertIn("rename from old-name.txt", rename_filtered)
        self.assertIn("rename to new-name.txt", rename_filtered)
        self.assertNotIn("delete-me.txt", rename_filtered)

        delete_filtered = GitService.filter_unified_diff(commit_diff, "delete-me.txt")
        self.assertIn("deleted file mode", delete_filtered)
        self.assertNotIn("new-name.txt", delete_filtered)

        binary_filtered = GitService.filter_unified_diff(commit_diff, "image.bin")
        self.assertIn("Binary files", binary_filtered)


if __name__ == "__main__":
    unittest.main()
