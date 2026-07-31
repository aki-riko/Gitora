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


class RemoteBranchCheckoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_deleted_local_branch_repo(self) -> tuple[Path, Path, str]:
        remote = init_bare_repo(self.root / "remote.git")
        seed = init_repo(self.root / "seed")
        write_file(seed, "base.txt", "base\n")
        commit_all(seed, "base")
        run_git(seed, "remote", "add", "origin", str(remote))
        run_git(seed, "push", "-u", "origin", "master")

        run_git(seed, "checkout", "-b", "codex/fix-one")
        write_file(seed, "fix.txt", "remote fix\n")
        commit_all(seed, "remote fix")
        run_git(seed, "push", "origin", "codex/fix-one")
        remote_commit = run_git(seed, "rev-parse", "HEAD").stdout.strip()

        clone = clone_repo(remote, self.root / "clone")
        run_git(
            clone,
            "checkout",
            "-b",
            "codex/fix-one",
            "--track",
            "origin/codex/fix-one",
        )
        run_git(clone, "checkout", "master")
        run_git(clone, "branch", "-D", "codex/fix-one")
        run_git(
            clone,
            "update-ref",
            "-d",
            "refs/remotes/origin/codex/fix-one",
        )
        return remote, clone, remote_commit

    def service_for(self, repo: Path) -> GitService:
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        return service

    def test_fetches_then_recreates_deleted_local_tracking_branch(self) -> None:
        _remote, clone, remote_commit = self.make_deleted_local_branch_repo()
        self.assertFalse(self.ref_exists(clone, "refs/heads/codex/fix-one"))
        self.assertFalse(
            self.ref_exists(clone, "refs/remotes/origin/codex/fix-one")
        )
        service = self.service_for(clone)
        changed: list[bool] = []
        service.statusChanged.connect(lambda: changed.append(True))

        ok, message = service.fetch_and_checkout_remote_branch(
            "origin/codex/fix-one", "codex/fix-one"
        )

        self.assertTrue(ok, message)
        self.assertIn("origin/codex/fix-one", message)
        self.assertTrue(
            self.ref_exists(clone, "refs/remotes/origin/codex/fix-one")
        )
        self.assertTrue(self.ref_exists(clone, "refs/heads/codex/fix-one"))
        self.assertEqual(
            run_git(clone, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            "codex/fix-one",
        )
        self.assertEqual(run_git(clone, "rev-parse", "HEAD").stdout.strip(), remote_commit)
        self.assertEqual(
            run_git(
                clone,
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
            ).stdout.strip(),
            "origin/codex/fix-one",
        )
        self.assertEqual(changed, [True])

    def test_bridge_runs_combined_operation_on_worker_thread(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        main_thread = threading.get_ident()
        worker_threads: list[int] = []
        calls: list[tuple[str, str]] = []
        started: list[str] = []
        finished: list[tuple[bool, str]] = []
        task_results: list[object] = []

        def fake_fetch_checkout(
            remote_branch: str, local_branch: str
        ) -> tuple[bool, str]:
            calls.append((remote_branch, local_branch))
            worker_threads.append(threading.get_ident())
            return True, f"checked out {remote_branch}"

        bridge._svc.fetch_and_checkout_remote_branch = fake_fetch_checkout  # type: ignore[method-assign]
        bridge.operationStarted.connect(started.append)
        bridge.operationFinished.connect(
            lambda ok, message: finished.append((ok, message))
        )
        try:
            signatures = {
                bytes(bridge.metaObject().method(index).methodSignature()).decode(
                    "ascii"
                )
                for index in range(bridge.metaObject().methodCount())
            }
            self.assertIn(
                "fetchAndCheckoutRemoteBranch(QString,QString)", signatures
            )
            task = bridge.fetchAndCheckoutRemoteBranch(
                "origin/codex/fix-one", "codex/fix-one"
            )
            task.succeeded.connect(task_results.append)

            self.assertTrue(
                self.wait_until(app, lambda: len(finished) == 1), finished
            )
            self.assertEqual(
                calls, [("origin/codex/fix-one", "codex/fix-one")]
            )
            self.assertEqual(len(worker_threads), 1)
            self.assertNotEqual(worker_threads[0], main_thread)
            self.assertEqual(started, ["正在获取并检出远程分支..."])
            self.assertEqual(
                finished, [(True, "checked out origin/codex/fix-one")]
            )
            self.assertEqual(
                task_results, [(True, "checked out origin/codex/fix-one")]
            )
        finally:
            bridge.deleteLater()
            app.processEvents()

    def test_branch_view_uses_combined_operation(self) -> None:
        view_source = (
            ROOT / "app_qml" / "qml" / "views" / "BranchView.qml"
        ).read_text(encoding="utf-8")
        delegate_source = (
            ROOT / "app_qml" / "qml" / "components" / "BranchRowDelegate.qml"
        ).read_text(encoding="utf-8")

        self.assertIn('text: control.isRemoteBranch ? "获取并检出"', delegate_source)
        self.assertIn('objectName: "remoteCheckoutDialogTitle"', view_source)
        self.assertIn('text: "获取并检出远程分支"', view_source)
        self.assertIn('confirmText: "获取并检出"', view_source)
        self.assertIn(
            "root._op(GitBridge.fetchAndCheckoutRemoteBranch(", view_source
        )
        self.assertNotIn(
            "root._op(GitBridge.checkoutRemoteBranch(", view_source
        )

    @staticmethod
    def ref_exists(repo: Path, ref: str) -> bool:
        return (
            run_git(repo, "show-ref", "--verify", "--quiet", ref, check=False).returncode
            == 0
        )

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
