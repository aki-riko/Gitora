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

    def test_reorder_persists_new_order(self) -> None:
        """拖动标签页改变顺序后，落盘顺序必须跟着变（不能被当成无变化跳过）。"""
        config_path = self.root / "reorder.json"
        manager = OpenedReposManager(config_path)
        repo_a = self.root / "repo-a"
        repo_b = self.root / "repo-b"
        repo_c = self.root / "repo-c"
        for repo in (repo_a, repo_b, repo_c):
            repo.mkdir()

        manager.replace([str(repo_a), str(repo_b), str(repo_c)], str(repo_a))
        # 把 repo-c 拖到最前面。
        manager.replace([str(repo_c), str(repo_a), str(repo_b)], str(repo_a))

        expected = [
            os.path.normpath(str(repo_c)),
            os.path.normpath(str(repo_a)),
            os.path.normpath(str(repo_b)),
        ]
        self.assertEqual(manager.get_all(), expected)
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["repos"], expected)
        # 活动仓库不受重排影响。
        self.assertEqual(saved["active"], os.path.normpath(str(repo_a)))

        # 重启后读回的仍是拖动后的顺序。
        self.assertEqual(OpenedReposManager(config_path).get_all(), expected)

    def test_stale_sequence_is_discarded(self) -> None:
        """线程池不保证完成顺序：迟到的旧快照不能覆盖新快照。"""
        config_path = self.root / "sequence.json"
        manager = OpenedReposManager(config_path)
        repo_a = self.root / "repo-a"
        repo_b = self.root / "repo-b"
        repo_a.mkdir()
        repo_b.mkdir()

        # seq=2 先落地（较新的快照：只剩 repo-b）
        manager.replace([str(repo_b)], str(repo_b), sequence=2)
        self.assertEqual(manager.get_all(), [os.path.normpath(str(repo_b))])

        # seq=1 迟到（较旧的快照：两个标签都在）——必须被丢弃
        manager.replace([str(repo_a), str(repo_b)], str(repo_a), sequence=1)
        self.assertEqual(manager.get_all(), [os.path.normpath(str(repo_b))])
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["repos"], [os.path.normpath(str(repo_b))])

        # 相同序号同样丢弃；更大的序号才生效
        manager.replace([str(repo_a)], str(repo_a), sequence=2)
        self.assertEqual(manager.get_all(), [os.path.normpath(str(repo_b))])
        manager.replace([str(repo_a)], str(repo_a), sequence=3)
        self.assertEqual(manager.get_all(), [os.path.normpath(str(repo_a))])

    def test_concurrent_replace_keeps_file_parseable(self) -> None:
        """多线程并发写盘不能产生坏 JSON 或半截文件。"""
        import threading

        config_path = self.root / "concurrent.json"
        manager = OpenedReposManager(config_path)
        repos = []
        for index in range(8):
            repo = self.root / f"repo-{index}"
            repo.mkdir()
            repos.append(str(repo))

        errors: list[BaseException] = []
        start = threading.Event()

        def writer(sequence: int) -> None:
            try:
                start.wait(5)
                subset = repos[: (sequence % len(repos)) + 1]
                for _ in range(20):
                    manager.replace(subset, subset[0], sequence=sequence)
                    # 并发读，确保读路径也不会看到半截状态
                    manager.get_snapshot()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(seq,)) for seq in range(1, 13)
        ]
        for thread in threads:
            thread.start()
        start.set()
        for thread in threads:
            thread.join(30)

        self.assertEqual(errors, [])
        # 文件必须始终是可解析的完整 JSON
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertIsInstance(saved["repos"], list)
        self.assertIn(saved["active"], saved["repos"])
        # 最终状态必须来自序号最大的那次写入
        self.assertEqual(
            saved["repos"],
            [os.path.normpath(path) for path in repos[:12 % len(repos) + 1]],
        )
        # 临时文件不能残留
        leftovers = list(self.root.glob(".concurrent.json.*"))
        self.assertEqual(leftovers, [])

    def test_save_is_atomic_and_leaves_no_temp_files(self) -> None:
        """写盘走临时文件 + 原子替换，写坏时不会毁掉已有快照。"""
        config_path = self.root / "atomic.json"
        manager = OpenedReposManager(config_path)
        repo_a = self.root / "repo-a"
        repo_a.mkdir()
        manager.replace([str(repo_a)], str(repo_a))
        good_content = config_path.read_text(encoding="utf-8")

        # 模拟替换阶段失败：已有文件必须保持原样，且不留临时文件
        import app.common.opened_repos as module_under_test

        original_replace = module_under_test.os.replace

        def failing_replace(src: str, dst: str) -> None:
            raise OSError("模拟原子替换失败")

        module_under_test.os.replace = failing_replace
        try:
            repo_b = self.root / "repo-b"
            repo_b.mkdir()
            manager.replace([str(repo_a), str(repo_b)], str(repo_b))
        finally:
            module_under_test.os.replace = original_replace

        self.assertEqual(config_path.read_text(encoding="utf-8"), good_content)
        self.assertEqual(list(self.root.glob(".atomic.json.*")), [])

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
        loop = QEventLoop()

        def on_restored(paths: object, active: object) -> None:
            restored.append(([str(item) for item in paths], str(active)))
            loop.quit()

        bridge.openedReposRestored.connect(on_restored)
        QTimer.singleShot(10000, loop.quit)
        bridge.restoreLastRepoAsync()
        loop.exec()

        # 必须发信号，否则前端永远停在“恢复中”，之后的快照都不会落盘。
        self.assertEqual(restored, [([], "")])
        self.assertEqual(bridge.repoPath, "")

    def test_restore_does_not_stat_paths_on_main_thread(self) -> None:
        """启动读快照必须在后台线程：exists() 遇到掉线网络盘会卡死主线程。"""
        import threading

        repo_a = init_repo(self.root / "repo-a")
        manager = OpenedReposManager(self.root / "threaded.json")
        manager.replace([str(repo_a)], str(repo_a))

        stat_threads: list[int] = []
        original_get_snapshot = manager.get_snapshot

        def recording_get_snapshot() -> tuple[list[str], str]:
            stat_threads.append(threading.get_ident())
            return original_get_snapshot()

        manager.get_snapshot = recording_get_snapshot
        opened_module.openedReposManager = manager
        recent_module.recentReposManager = RecentReposManager(
            self.root / "recent.json"
        )

        bridge = self._make_bridge()
        loop = QEventLoop()
        bridge.openedReposRestored.connect(lambda *_: loop.quit())
        QTimer.singleShot(10000, loop.quit)
        bridge.restoreLastRepoAsync()
        loop.exec()

        self.assertEqual(len(stat_threads), 1, stat_threads)
        self.assertNotEqual(
            stat_threads[0],
            threading.get_ident(),
            "快照读取跑在了主线程上",
        )

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
