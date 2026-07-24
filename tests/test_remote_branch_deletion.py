# coding: utf-8
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

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


ROOT = Path(__file__).resolve().parents[1]


class RemoteBranchDeletionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_remote_branch_repo(self) -> tuple[Path, Path]:
        remote = init_bare_repo(self.root / "remote.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "base.txt", "base\n")
        commit_all(seed, "base")
        run_git(seed, "remote", "add", "origin", str(remote))
        run_git(seed, "push", "-u", "origin", "master")
        run_git(seed, "checkout", "-b", "feature/nested")
        write_file(seed, "feature.txt", "feature\n")
        commit_all(seed, "feature")
        run_git(seed, "push", "origin", "feature/nested")

        clone = clone_repo(remote, self.root / "clone")
        run_git(clone, "branch", "feature/nested", "origin/feature/nested")
        return remote, clone

    def service_for(self, repo: Path) -> GitService:
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        return service

    def test_service_deletes_real_remote_branch_and_keeps_local_branch(self) -> None:
        remote, clone = self.make_remote_branch_repo()
        service = self.service_for(clone)
        changed: list[bool] = []
        service.statusChanged.connect(lambda: changed.append(True))

        ok, message = service.delete_remote_branch("origin/feature/nested")

        self.assertTrue(ok, message)
        self.assertIn("origin/feature/nested", message)
        self.assertFalse(self.ref_exists(remote, "refs/heads/feature/nested"))
        self.assertFalse(
            self.ref_exists(clone, "refs/remotes/origin/feature/nested")
        )
        self.assertTrue(self.ref_exists(clone, "refs/heads/feature/nested"))
        self.assertTrue(self.ref_exists(remote, "refs/heads/master"))
        self.assertEqual(changed, [True])

    def test_service_rejects_unknown_remote_without_mutating_repository(self) -> None:
        remote, clone = self.make_remote_branch_repo()
        service = self.service_for(clone)

        ok, message = service.delete_remote_branch("missing/feature/nested")

        self.assertFalse(ok)
        self.assertIn("远程", message)
        self.assertTrue(self.ref_exists(remote, "refs/heads/feature/nested"))
        self.assertTrue(
            self.ref_exists(clone, "refs/remotes/origin/feature/nested")
        )

        ok, message = service.delete_remote_branch("origin/../feature")

        self.assertFalse(ok)
        self.assertIn("非法", message)
        self.assertTrue(self.ref_exists(remote, "refs/heads/feature/nested"))

    def test_service_treats_already_missing_remote_branch_as_success(self) -> None:
        remote, clone = self.make_remote_branch_repo()
        run_git(remote, "update-ref", "-d", "refs/heads/feature/nested")
        service = self.service_for(clone)

        ok, message = service.delete_remote_branch("origin/feature/nested")

        self.assertTrue(ok, message)
        self.assertFalse(self.ref_exists(remote, "refs/heads/feature/nested"))
        self.assertFalse(
            self.ref_exists(clone, "refs/remotes/origin/feature/nested")
        )
        self.assertTrue(self.ref_exists(clone, "refs/heads/feature/nested"))
        self.assertTrue(self.ref_exists(remote, "refs/heads/master"))

    def test_service_reports_remote_rejection_without_mutating_repository(self) -> None:
        remote, clone = self.make_remote_branch_repo()
        run_git(remote, "config", "receive.denyDeletes", "true")
        service = self.service_for(clone)

        ok, message = service.delete_remote_branch("origin/feature/nested")

        self.assertFalse(ok)
        self.assertTrue(message.strip())
        self.assertTrue(self.ref_exists(remote, "refs/heads/feature/nested"))
        self.assertTrue(
            self.ref_exists(clone, "refs/remotes/origin/feature/nested")
        )
        self.assertTrue(self.ref_exists(clone, "refs/heads/feature/nested"))

    def test_bridge_deletes_remote_branch_on_worker_thread(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        main_thread = threading.get_ident()
        worker_threads: list[int] = []
        calls: list[str] = []
        started: list[str] = []
        finished: list[tuple[bool, str]] = []

        def fake_delete(remote_branch: str) -> tuple[bool, str]:
            calls.append(remote_branch)
            worker_threads.append(threading.get_ident())
            return True, f"deleted {remote_branch}"

        bridge._svc.delete_remote_branch = fake_delete  # type: ignore[method-assign]
        bridge.operationStarted.connect(started.append)

        def on_finished(ok: bool, message: str) -> None:
            finished.append((ok, message))

        bridge.operationFinished.connect(on_finished)
        try:
            signatures = {
                bytes(bridge.metaObject().method(index).methodSignature()).decode(
                    "ascii"
                )
                for index in range(bridge.metaObject().methodCount())
            }
            self.assertIn("deleteRemoteBranch(QString)", signatures)
            bridge.deleteRemoteBranch("origin/feature/nested")
            self.assertTrue(
                self.wait_until(app, lambda: len(finished) == 1), finished
            )
            self.assertEqual(calls, ["origin/feature/nested"])
            self.assertEqual(len(worker_threads), 1)
            self.assertNotEqual(worker_threads[0], main_thread)
            self.assertEqual(
                started, ["正在删除远程分支 origin/feature/nested..."]
            )
            self.assertEqual(
                finished, [(True, "deleted origin/feature/nested")]
            )
        finally:
            bridge.deleteLater()
            app.processEvents()

    def test_branch_view_requires_danger_confirmation(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "views" / "BranchView.qml"
        ).read_text(encoding="utf-8")

        self.assertIn('objectName: "deleteRemoteBranchButton"', source)
        self.assertIn('id: deleteRemoteBranchDanger', source)
        self.assertIn('title: "确认删除远程分支"', source)
        self.assertIn('countdown: 3', source)
        self.assertIn(
            'GitBridge.deleteRemoteBranch(root._remoteDeleteTarget)', source
        )

    @staticmethod
    def ref_exists(repo: Path, ref: str) -> bool:
        result = run_git(
            repo, "show-ref", "--verify", "--quiet", ref, check=False
        )
        return result.returncode == 0

    @staticmethod
    def wait_until(
        app: QCoreApplication, predicate, timeout: float = 5.0
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        app.processEvents()
        return bool(predicate())


if __name__ == "__main__":
    unittest.main()
