# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
