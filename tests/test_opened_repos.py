# coding: utf-8
"""已打开仓库会话快照：落盘、清理与启动恢复。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.common import opened_repos as opened_module
from app.common import recent_repos as recent_module
from app.common.opened_repos import OpenedReposManager
from app.common.recent_repos import RecentReposManager
from app_qml.backend.git_bridge import GitBridge

from git_test_utils import init_repo


class OpenedReposManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_manager(self, filename: str = "opened_repos.json") -> OpenedReposManager:
        return OpenedReposManager(self.root / filename)

    def test_replace_persists_full_tab_set_and_active(self) -> None:
        config_path = self.root / "opened_repos.json"
        manager = OpenedReposManager(config_path)
        repo_a = self.root / "repo-a"
        repo_b = self.root / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()

        manager.replace([str(repo_a), str(repo_b)], str(repo_b))

        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["repos"],
            [os.path.normpath(str(repo_a)), os.path.normpath(str(repo_b))],
        )
        self.assertEqual(saved["active"], os.path.normpath(str(repo_b)))

        # 重新构造(等价于重启进程)后必须读回全部标签页。
        reloaded = OpenedReposManager(config_path)
        self.assertEqual(
            reloaded.get_all(),
            [os.path.normpath(str(repo_a)), os.path.normpath(str(repo_b))],
        )
        self.assertEqual(reloaded.get_active(), os.path.normpath(str(repo_b)))

    def test_replace_deduplicates_and_falls_back_active(self) -> None:
        manager = self.make_manager()
        repo_a = self.root / "repo-a"
        repo_b = self.root / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()
        alternate_path = (
            repo_a.as_posix()
            if os.name == "nt"
            else f"{repo_a.parent}{os.sep}.{os.sep}{repo_a.name}"
        )

        manager.replace([str(repo_a), alternate_path, str(repo_b)], "")

        self.assertEqual(
            manager.get_all(),
            [os.path.normpath(str(repo_a)), os.path.normpath(str(repo_b))],
        )
        # active 为空时回退到第一项，保证启动一定有仓库可打开。
        self.assertEqual(manager.get_active(), os.path.normpath(str(repo_a)))

        # active 指向不在列表里的路径时同样回退。
        manager.replace([str(repo_b)], str(repo_a))
        self.assertEqual(manager.get_active(), os.path.normpath(str(repo_b)))

    def test_get_all_prunes_missing_directories(self) -> None:
        manager = self.make_manager()
        repo_a = self.root / "repo-a"
        repo_b = self.root / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()
        manager.replace([str(repo_a), str(repo_b)], str(repo_b))

        repo_b.rmdir()

        self.assertEqual(manager.get_all(), [os.path.normpath(str(repo_a))])
        self.assertEqual(manager.get_active(), os.path.normpath(str(repo_a)))

    def test_corrupt_config_is_tolerated(self) -> None:
        config_path = self.root / "broken.json"
        config_path.write_text("{not json", encoding="utf-8")
        manager = OpenedReposManager(config_path)
        self.assertEqual(manager.get_all(), [])
        self.assertEqual(manager.get_active(), "")

        config_path.write_text(json.dumps(["list-not-dict"]), encoding="utf-8")
        manager = OpenedReposManager(config_path)
        self.assertEqual(manager.get_all(), [])

        config_path.write_text(
            json.dumps({"repos": "not-a-list", "active": 42}), encoding="utf-8"
        )
        manager = OpenedReposManager(config_path)
        self.assertEqual(manager.get_all(), [])
        self.assertEqual(manager.get_active(), "")

    def test_clear_empties_snapshot(self) -> None:
        manager = self.make_manager()
        repo_a = self.root / "repo-a"
        repo_a.mkdir()
        manager.replace([str(repo_a)], str(repo_a))
        manager.clear()
        self.assertEqual(manager.get_all(), [])
        self.assertEqual(manager.get_active(), "")


class OpenedReposRestoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self._previous_opened = opened_module.openedReposManager
        self._previous_recent = recent_module.recentReposManager

    def tearDown(self) -> None:
        opened_module.openedReposManager = self._previous_opened
        recent_module.recentReposManager = self._previous_recent
        self.app.processEvents()
        self._tmp.cleanup()

    def _make_bridge(self) -> GitBridge:
        bridge = GitBridge()
        self.addCleanup(bridge.deleteLater)
        self.addCleanup(bridge._poll_timer.stop)
        return bridge

    def test_restore_reopens_every_tab_from_last_session(self) -> None:
        repo_a = init_repo(self.root / "repo-a")
        repo_b = init_repo(self.root / "repo-b")
        repo_c = init_repo(self.root / "repo-c")

        opened_module.openedReposManager = OpenedReposManager(
            self.root / "opened.json"
        )
        opened_module.openedReposManager.replace(
            [str(repo_a), str(repo_b), str(repo_c)], str(repo_b)
        )
        recent_module.recentReposManager = RecentReposManager(
            self.root / "recent.json"
        )
        recent_module.recentReposManager.add(str(repo_c))

        bridge = self._make_bridge()
        restored: list[tuple[list[str], str]] = []
        opened: list[tuple[bool, str]] = []
        loop = QEventLoop()

        bridge.openedReposRestored.connect(
            lambda paths, active: restored.append(
                ([str(item) for item in paths], str(active))
            )
        )

        def on_opened(ok: bool, payload: str) -> None:
            opened.append((ok, payload))
            loop.quit()

        bridge.repoOpened.connect(on_opened)
        QTimer.singleShot(10000, loop.quit)
        bridge.restoreLastRepoAsync()
        loop.exec()
        bridge.repoOpened.disconnect(on_opened)

        # 全部标签页都要回到前端，而不是只有最近一个。
        self.assertEqual(len(restored), 1)
        restored_paths, restored_active = restored[0]
        self.assertEqual(
            restored_paths,
            [
                os.path.normpath(str(repo_a)),
                os.path.normpath(str(repo_b)),
                os.path.normpath(str(repo_c)),
            ],
        )
        self.assertEqual(restored_active, os.path.normpath(str(repo_b)))
        # 只有活动仓库被真正打开，其余标签保持未读取。
        self.assertEqual(opened, [(True, str(repo_b))])
        self.assertEqual(bridge.repoPath, str(repo_b))

    def test_restore_falls_back_to_recent_repo_without_snapshot(self) -> None:
        repo_a = init_repo(self.root / "repo-a")
        repo_b = init_repo(self.root / "repo-b")

        opened_module.openedReposManager = OpenedReposManager(
            self.root / "empty.json"
        )
        recent_module.recentReposManager = RecentReposManager(
            self.root / "recent.json"
        )
        recent_module.recentReposManager.add(str(repo_a))
        recent_module.recentReposManager.add(str(repo_b))

        bridge = self._make_bridge()
        restored: list[tuple[list[str], str]] = []
        loop = QEventLoop()
        bridge.openedReposRestored.connect(
            lambda paths, active: restored.append(
                ([str(item) for item in paths], str(active))
            )
        )
        bridge.repoOpened.connect(lambda *_: loop.quit())
        QTimer.singleShot(10000, loop.quit)
        bridge.restoreLastRepoAsync()
        loop.exec()

        self.assertEqual(restored, [([str(repo_b)], str(repo_b))])
        self.assertEqual(bridge.repoPath, str(repo_b))

    def test_restore_emits_even_when_nothing_to_restore(self) -> None:
        opened_module.openedReposManager = OpenedReposManager(
            self.root / "empty.json"
        )
        recent_module.recentReposManager = RecentReposManager(
            self.root / "recent-empty.json"
        )

        bridge = self._make_bridge()
        restored: list[tuple[list[str], str]] = []
        bridge.openedReposRestored.connect(
            lambda paths, active: restored.append(
                ([str(item) for item in paths], str(active))
            )
        )
        bridge.restoreLastRepoAsync()
        self.app.processEvents()

        # 必须发信号，否则前端永远停在“恢复中”，之后的快照都不会落盘。
        self.assertEqual(restored, [([], "")])
        self.assertEqual(bridge.repoPath, "")

    def test_save_opened_repos_slot_writes_snapshot(self) -> None:
        repo_a = init_repo(self.root / "repo-a")
        repo_b = init_repo(self.root / "repo-b")
        config_path = self.root / "saved.json"
        opened_module.openedReposManager = OpenedReposManager(config_path)

        bridge = self._make_bridge()
        handle = bridge.saveOpenedRepos([str(repo_a), str(repo_b)], str(repo_b))

        loop = QEventLoop()
        QTimer.singleShot(5000, loop.quit)
        if handle is not None and hasattr(handle, "finished"):
            handle.finished.connect(loop.quit)
            loop.exec()
        else:
            QTimer.singleShot(300, loop.quit)
            loop.exec()

        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["repos"],
            [os.path.normpath(str(repo_a)), os.path.normpath(str(repo_b))],
        )
        self.assertEqual(saved["active"], os.path.normpath(str(repo_b)))


if __name__ == "__main__":
    unittest.main()
