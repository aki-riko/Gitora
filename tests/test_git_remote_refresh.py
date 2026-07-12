# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.common.git_service import GitService
from app_qml.backend.git_bridge import GitBridge

from git_test_utils import (
    clone_repo,
    commit_all,
    init_bare_repo,
    init_repo,
    run_git,
    write_file,
)


class GitRemoteRefreshTest(unittest.TestCase):
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

    def test_fetch_prunes_deleted_remote_tracking_branch(self) -> None:
        remote = init_bare_repo(self.root / "remote.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "base.txt", "base\n")
        commit_all(seed, "base")
        run_git(seed, "remote", "add", "upstream", str(remote))
        run_git(seed, "push", "-u", "upstream", "master")
        run_git(seed, "checkout", "-b", "feature")
        write_file(seed, "feature.txt", "feature\n")
        commit_all(seed, "feature")
        run_git(seed, "push", "upstream", "feature")

        clone = clone_repo(remote, self.root / "clone")
        run_git(clone, "remote", "rename", "origin", "upstream")
        run_git(clone, "config", "fetch.prune", "false")
        service = self.service_for(clone)
        self.assertIn("upstream/feature", self.remote_branch_names(service))
        self.assertTrue(self.ref_exists(clone, "refs/remotes/upstream/feature"))

        run_git(seed, "push", "upstream", "--delete", "feature")
        missing_remote = run_git(remote, "rev-parse", "refs/heads/feature", check=False)
        self.assertNotEqual(missing_remote.returncode, 0)

        ok, msg = self.wait_operation(service, lambda: service.fetch("upstream"))
        self.assertTrue(ok, msg)
        self.assertNotIn("upstream/feature", self.remote_branch_names(service))
        self.assertFalse(self.ref_exists(clone, "refs/remotes/upstream/feature"))
        self.assertIn("upstream/master", self.remote_branch_names(service))

    def test_fetch_all_updates_and_prunes_every_remote(self) -> None:
        origin, upstream, seed, clone = self.make_two_remote_repo()
        self.push_branch(seed, "origin", "old-origin")
        self.push_branch(seed, "upstream", "old-upstream")
        run_git(clone, "fetch", "origin")
        run_git(clone, "fetch", "upstream")
        self.assertTrue(self.ref_exists(clone, "refs/remotes/origin/old-origin"))
        self.assertTrue(self.ref_exists(clone, "refs/remotes/upstream/old-upstream"))

        run_git(seed, "push", "origin", "--delete", "old-origin")
        run_git(seed, "push", "upstream", "--delete", "old-upstream")
        self.push_branch(seed, "origin", "fresh-origin")
        self.push_branch(seed, "upstream", "fresh-upstream")

        service = self.service_for(clone)
        ok, msg = self.wait_operation(service, service.fetch_all)
        self.assertTrue(ok, msg)

        names = self.remote_branch_names(service)
        self.assertNotIn("origin/old-origin", names)
        self.assertNotIn("upstream/old-upstream", names)
        self.assertIn("origin/fresh-origin", names)
        self.assertIn("upstream/fresh-upstream", names)
        self.assertFalse(self.ref_exists(clone, "refs/remotes/origin/old-origin"))
        self.assertFalse(self.ref_exists(clone, "refs/remotes/upstream/old-upstream"))
        self.assertTrue(self.ref_exists(clone, "refs/remotes/origin/fresh-origin"))
        self.assertTrue(self.ref_exists(clone, "refs/remotes/upstream/fresh-upstream"))
        self.assertEqual(run_git(origin, "rev-parse", "refs/heads/fresh-origin").returncode, 0)
        self.assertEqual(run_git(upstream, "rev-parse", "refs/heads/fresh-upstream").returncode, 0)

    def test_branch_view_fetch_all_wiring(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        calls = []
        bridge._svc.fetch_all = lambda: calls.append("fetch_all")  # type: ignore[method-assign]

        try:
            bridge.fetchAll()
            self.assertEqual(calls, ["fetch_all"])
            qml = (
                Path(__file__).resolve().parents[1]
                / "app_qml"
                / "qml"
                / "views"
                / "BranchView.qml"
            ).read_text(encoding="utf-8")
            self.assertIn("onClicked: GitBridge.fetchAll()", qml)
            self.assertNotIn("onClicked: GitBridge.fetch()", qml)
        finally:
            bridge.deleteLater()
            app.processEvents()

    def make_two_remote_repo(self) -> tuple[Path, Path, Path, Path]:
        origin = init_bare_repo(self.root / "origin.git")
        upstream = init_bare_repo(self.root / "upstream.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "base.txt", "base\n")
        commit_all(seed, "base")
        run_git(seed, "remote", "add", "origin", str(origin))
        run_git(seed, "remote", "add", "upstream", str(upstream))
        run_git(seed, "push", "-u", "origin", "master")
        run_git(seed, "push", "upstream", "master")

        clone = clone_repo(origin, self.root / "clone")
        run_git(clone, "remote", "add", "upstream", str(upstream))
        run_git(clone, "config", "fetch.prune", "false")
        run_git(clone, "fetch", "upstream")
        return origin, upstream, seed, clone

    @staticmethod
    def push_branch(seed: Path, remote: str, branch: str) -> None:
        run_git(seed, "checkout", "master")
        run_git(seed, "checkout", "-b", branch)
        write_file(seed, f"{branch}.txt", f"{branch}\n")
        commit_all(seed, branch)
        run_git(seed, "push", remote, branch)

    @staticmethod
    def remote_branch_names(service: GitService) -> set[str]:
        return {branch.name for branch in service.get_branches() if branch.is_remote}

    @staticmethod
    def ref_exists(repo: Path, ref: str) -> bool:
        result = run_git(repo, "show-ref", "--verify", "--quiet", ref, check=False)
        return result.returncode == 0


if __name__ == "__main__":
    unittest.main()
