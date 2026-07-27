# coding: utf-8
"""批量冲突解决必须使用真实冲突输入，并保持后台执行契约。"""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread

from app.common.git_service import GitService
from app_qml.backend.git_bridge import GitBridge
from git_test_utils import commit_all, init_repo, run_git, write_file


class ConflictBulkResolutionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_conflict_repo(self, name: str) -> tuple[Path, GitService]:
        repo = init_repo(self.root / name)
        for path in ("first.txt", "nested/second.txt"):
            write_file(repo, path, "base\n")
        commit_all(repo, "base")
        run_git(repo, "checkout", "-b", "incoming")
        for path in ("first.txt", "nested/second.txt"):
            write_file(repo, path, "remote\n")
        commit_all(repo, "incoming")
        run_git(repo, "checkout", "master")
        for path in ("first.txt", "nested/second.txt"):
            write_file(repo, path, "local\n")
        commit_all(repo, "local")
        merge = run_git(repo, "merge", "incoming", check=False)
        self.assertNotEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        self.assertEqual(
            [conflict.path for conflict in service.get_conflicts()],
            ["first.txt", "nested/second.txt"],
        )
        return repo, service

    def _assert_all_staged(self, repo: Path, expected: str) -> None:
        for path in ("first.txt", "nested/second.txt"):
            self.assertEqual((repo / path).read_text(encoding="utf-8"), expected)
        self.assertEqual(
            run_git(repo, "ls-files", "--unmerged").stdout,
            "",
        )
        self.assertEqual(
            {
                line.split(maxsplit=3)[3]
                for line in run_git(repo, "ls-files", "--stage").stdout.splitlines()
            },
            {"first.txt", "nested/second.txt"},
        )

    def test_all_local_and_remote_priorities_resolve_real_conflicts(self) -> None:
        local_repo, local_service = self._make_conflict_repo("local-priority")
        ok, message = local_service.resolve_all_conflicts_with_ours()
        self.assertTrue(ok, message)
        self.assertEqual(message, "已按本地版本解决 2 个冲突")
        self._assert_all_staged(local_repo, "local\n")

        remote_repo, remote_service = self._make_conflict_repo("remote-priority")
        ok, message = remote_service.resolve_all_conflicts_with_theirs()
        self.assertTrue(ok, message)
        self.assertEqual(message, "已按远程版本解决 2 个冲突")
        self._assert_all_staged(remote_repo, "remote\n")

    def test_bridge_bulk_resolution_runs_off_gui_thread(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        gui_thread = QThread.currentThread()
        worker_started = threading.Event()
        worker_release = threading.Event()
        observed: dict[str, object] = {}
        results: list[object] = []

        def fake_resolve() -> tuple[bool, str]:
            observed["thread"] = QThread.currentThread()
            worker_started.set()
            worker_release.wait(5)
            return True, "done"

        bridge._svc.resolve_all_conflicts_with_ours = fake_resolve  # type: ignore[method-assign]
        try:
            handle = bridge.resolveAllWithOurs()
            handle.succeeded.connect(results.append)
            self.assertTrue(worker_started.wait(5), "后台冲突任务未启动")
            self.assertIsNot(observed["thread"], gui_thread)
            self.assertEqual(results, [])
            worker_release.set()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not results:
                app.processEvents()
                time.sleep(0.01)
            self.assertEqual(results, [(True, "done")])
        finally:
            worker_release.set()
            bridge.deleteLater()
            app.processEvents()


class ConflictViewContractTest(unittest.TestCase):
    def test_bulk_buttons_and_shared_three_second_cooldown_are_wired(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "app_qml" / "qml" / "views" / "ConflictView.qml"
        ).read_text(encoding="utf-8")
        self.assertIn('root._resolveText("全部本地优先")', source)
        self.assertIn('root._resolveText("全部远程优先")', source)
        self.assertIn("GitBridge.resolveAllWithOurs()", source)
        self.assertIn("GitBridge.resolveAllWithTheirs()", source)
        self.assertIn("root.resolveCooldown = 3", source)
        self.assertIn('root._resolveText("本地优先")', source)
        self.assertIn('root._resolveText("远程优先")', source)


if __name__ == "__main__":
    unittest.main()
