# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.common import recent_repos as recent_module
from app.common.recent_repos import RecentReposManager
from app_qml.backend.git_bridge import GitBridge

from git_test_utils import init_repo


class RecentReposTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_manager(self, filename: str) -> RecentReposManager:
        manager = RecentReposManager.__new__(RecentReposManager)
        manager.file_path = self.root / filename
        manager._repos = []
        manager._save()
        return manager

    def test_manager_deduplicates_limits_and_prunes_missing_paths(self) -> None:
        manager = self.make_manager("recent_repos.json")
        repos = []
        for i in range(12):
            repo_path = self.root / f"repo-{i}"
            repo_path.mkdir()
            repos.append(str(repo_path))
            manager.add(str(repo_path))

        self.assertEqual(manager.get_all(), list(reversed(repos[-10:])))

        manager.add(repos[5])
        current = manager.get_all()
        self.assertEqual(current[0], repos[5])
        self.assertEqual(current.count(repos[5]), 1)
        self.assertLessEqual(len(current), manager.MAX_RECENT)

        Path(repos[5]).rmdir()
        self.assertNotIn(repos[5], manager.get_all())

        manager.clear()
        self.assertEqual(manager.get_all(), [])

    def test_git_bridge_recent_repo_slots_use_temp_manager_and_real_repos(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        repo_a = init_repo(self.root / "repo-a")
        repo_b = init_repo(self.root / "repo-b")
        manager = self.make_manager("bridge_recent_repos.json")
        previous_manager = recent_module.recentReposManager
        bridge = GitBridge()
        recent_module.recentReposManager = manager
        repo_path_events: list[str] = []
        status_events: list[bool] = []
        bridge.repoPathChanged.connect(repo_path_events.append)
        bridge.statusChanged.connect(lambda: status_events.append(True))

        try:
            self.assertTrue(bridge.setRepoPath(str(repo_a)))
            self.assertEqual(bridge.getRecentRepos(), [str(repo_a)])
            self.assertEqual(repo_path_events, [str(repo_a)])
            self.assertEqual(status_events, [])

            repo_path_events.clear()
            status_events.clear()

            result: dict[str, object] = {}
            loop = QEventLoop()

            def on_opened(ok: bool, payload: str) -> None:
                result["ok"] = ok
                result["payload"] = payload
                loop.quit()

            bridge.repoOpened.connect(on_opened)
            QTimer.singleShot(10000, loop.quit)
            bridge.openRepoAsync(str(repo_b))
            loop.exec()
            bridge.repoOpened.disconnect(on_opened)

            self.assertTrue(result.get("ok"), result)
            self.assertEqual(bridge.getRecentRepos(), [str(repo_b), str(repo_a)])
            self.assertEqual(repo_path_events, [str(repo_b)])
            self.assertEqual(status_events, [])

            bridge.removeRecentRepo(str(repo_b))
            self.assertEqual(bridge.getRecentRepos(), [str(repo_a)])

            bridge.clearRecentRepos()
            self.assertEqual(bridge.getRecentRepos(), [])
        finally:
            bridge._poll_timer.stop()
            bridge.deleteLater()
            recent_module.recentReposManager = previous_manager
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
