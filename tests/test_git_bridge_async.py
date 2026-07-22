# coding: utf-8
from __future__ import annotations

import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication

from app.common.git_service import (
    CommitInfo,
    FileChange,
    FileStatus,
    SubmoduleInfo,
    WorktreeInfo,
)
from app_qml.backend.git_bridge import GitBridge


class GitBridgeAsyncTest(unittest.TestCase):
    def test_internal_status_change_invalidates_poll_baseline_without_duplicate(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        bridge._svc._repo_path = "repo"
        bridge._poll_fingerprint = "before"
        emitted: list[bool] = []
        bridge.statusChanged.connect(lambda: emitted.append(True))

        try:
            old_generation = bridge._poll_generation
            bridge._svc.statusChanged.emit()

            self.assertEqual(emitted, [True])
            self.assertEqual(bridge._poll_fingerprint, "")
            self.assertGreater(bridge._poll_generation, old_generation)

            bridge._poll_busy = True
            bridge._on_fingerprint_ready(
                "repo", "after", bridge._poll_generation
            )
            self.assertEqual(bridge._poll_fingerprint, "after")
            self.assertEqual(emitted, [True])
        finally:
            bridge.deleteLater()
            app.processEvents()

    def test_stale_poll_result_cannot_restore_pre_operation_baseline(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        bridge._svc._repo_path = "repo"
        bridge._poll_fingerprint = "before"

        try:
            stale_generation = bridge._poll_generation
            bridge._poll_busy = True
            bridge._svc.statusChanged.emit()
            bridge._on_fingerprint_ready("repo", "stale", stale_generation)

            self.assertEqual(bridge._poll_fingerprint, "")
            self.assertFalse(bridge._poll_busy)
        finally:
            bridge.deleteLater()
            app.processEvents()

    def test_quick_commit_push_emits_dedicated_completion_signal(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        emitted: list[tuple[bool, str]] = []
        seen: dict[str, str] = {}

        def fake_quick_commit_push(message: str, callback=None):
            seen["message"] = message
            callback(False, "仓库被占用")

        bridge._svc.quick_commit_push = fake_quick_commit_push  # type: ignore[method-assign]
        bridge.quickCommitPushFinished.connect(
            lambda ok, msg: emitted.append((ok, msg))
        )

        try:
            bridge.quickCommitPush("保留这条提交信息")
            self.assertEqual(seen["message"], "保留这条提交信息")
            self.assertEqual(emitted, [(False, "仓库被占用")])
        finally:
            bridge.deleteLater()
            app.processEvents()

    def test_poll_interval_is_exposed_for_page_level_probes(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()

        try:
            self.assertEqual(bridge.pollIntervalMs, bridge._POLL_INTERVAL_MS)
        finally:
            bridge.deleteLater()
            app.processEvents()

    def test_status_result_replaces_backend_model(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        bridge._svc._repo_path = "repo"
        bridge._svc.get_status_at = lambda repo: [  # type: ignore[method-assign]
            FileChange(f"{repo}/main.py", FileStatus.MODIFIED, False)
        ]
        bridge._svc.get_current_branch_at = lambda _repo: "master"  # type: ignore[method-assign]
        emitted: list[tuple[str, int]] = []
        bridge.statusReady.connect(lambda repo, count: emitted.append((repo, count)))

        bridge.requestStatus()

        self.assertTrue(self._wait_until(app, lambda: emitted == [("repo", 1)]))
        self.assertEqual(bridge.fileChangeModel.count, 1)
        self.assertTrue(bridge.fileChangeModel.contains("repo/main.py", False))
        bridge.deleteLater()
        app.processEvents()

    def test_stale_status_result_does_not_replace_current_repo_model(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        bridge._svc._repo_path = "repo-new"

        bridge._apply_status_result(
            "repo-old",
            [FileChange("stale.txt", FileStatus.MODIFIED, False)],
            "master",
        )

        self.assertEqual(bridge.fileChangeModel.count, 0)
        bridge.deleteLater()
        app.processEvents()

    def _configure_delayed_search(self, bridge: GitBridge):
        started = [threading.Event() for _ in range(3)]
        release = [threading.Event() for _ in range(3)]
        calls: list[str] = []
        emitted: list[str] = []

        def fake_search(repo_path: str, query: str, search_type: str, count: int):
            index = len(calls)
            calls.append(query)
            started[index].set()
            release[index].wait(5)
            return [CommitInfo(f"hash-{index}", f"h-{index}", "author", "", "", query)]

        bridge._svc.search_commits_at = fake_search  # type: ignore[method-assign]
        bridge.searchReady.connect(lambda _repo, items: emitted.append(items[0]["message"]))
        return started, release, calls, emitted

    def test_latest_search_request_wins(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()
        bridge._svc._repo_path = "repo"
        started, release, calls, emitted = self._configure_delayed_search(bridge)
        self.addCleanup(app.processEvents)
        self.addCleanup(bridge.deleteLater)
        for event in release:
            self.addCleanup(event.set)

        for index, query in enumerate(("a", "b", "a")):
            bridge.requestSearch(query, "all")
            self.assertTrue(started[index].wait(5), f"request {index} did not start")

        release[2].set()
        self.assertTrue(self._wait_until(app, lambda: emitted == ["a"]))
        release[0].set()
        release[1].set()
        time.sleep(0.1)
        app.processEvents()
        self.assertEqual(calls, ["a", "b", "a"])
        self.assertEqual(emitted, ["a"])

    def test_latest_tag_request_wins_across_a_b_a_switch(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()

        started = [threading.Event() for _ in range(3)]
        release = [threading.Event() for _ in range(3)]
        finished = [threading.Event() for _ in range(3)]
        call_lock = threading.Lock()
        calls: list[str] = []
        emitted: list[tuple[str, str]] = []

        def fake_get_tags_at(repo_path: str):
            with call_lock:
                index = len(calls)
                calls.append(repo_path)
            started[index].set()
            release[index].wait(5)
            finished[index].set()
            return [(f"tag-{index}", f"hash-{index}", "")]

        bridge._svc.get_tags_at = fake_get_tags_at  # type: ignore[method-assign]
        bridge.tagsReady.connect(
            lambda repo, items: emitted.append((repo, items[0]["name"]))
        )

        try:
            for index, repo in enumerate(("repo-a", "repo-b", "repo-a")):
                bridge._svc._repo_path = repo
                bridge.requestTags()
                self.assertTrue(started[index].wait(5), f"request {index} did not start")

            release[2].set()
            self.assertTrue(self._wait_until(app, lambda: len(emitted) == 1))
            release[0].set()
            release[1].set()
            self.assertTrue(self._wait_until(app, lambda: all(event.is_set() for event in finished)))
            time.sleep(0.1)
            app.processEvents()

            self.assertEqual(calls, ["repo-a", "repo-b", "repo-a"])
            self.assertEqual(emitted, [("repo-a", "tag-2")])
        finally:
            for event in release:
                event.set()
            bridge.deleteLater()
            app.processEvents()

    def test_latest_advanced_state_request_wins_across_a_b_a_switch(self) -> None:
        app = QCoreApplication.instance() or QCoreApplication([])
        bridge = GitBridge()
        bridge._poll_timer.stop()

        started = [threading.Event() for _ in range(3)]
        release = [threading.Event() for _ in range(3)]
        calls: list[str] = []
        emitted: list[tuple[str, str, str]] = []
        call_lock = threading.Lock()

        def fake_worktrees(repo_path: str):
            with call_lock:
                index = len(calls)
                calls.append(repo_path)
            started[index].set()
            release[index].wait(5)
            return [WorktreeInfo(path=f"{repo_path}/worktree-{index}")]

        def fake_submodules(repo_path: str):
            return [SubmoduleInfo(path=f"{repo_path}/submodule")]

        bridge._svc.list_worktrees_at = fake_worktrees  # type: ignore[method-assign]
        bridge._svc.list_submodules_at = fake_submodules  # type: ignore[method-assign]
        bridge.advancedStateReady.connect(
            lambda repo, worktrees, submodules: emitted.append(
                (repo, worktrees[0]["path"], submodules[0]["path"])
            )
        )

        try:
            for index, repo in enumerate(("repo-a", "repo-b", "repo-a")):
                bridge._svc._repo_path = repo
                bridge.requestAdvancedState()
                self.assertTrue(started[index].wait(5), f"request {index} did not start")

            release[2].set()
            self.assertTrue(self._wait_until(app, lambda: len(emitted) == 1))
            release[0].set()
            release[1].set()
            time.sleep(0.1)
            app.processEvents()

            self.assertEqual(calls, ["repo-a", "repo-b", "repo-a"])
            self.assertEqual(
                emitted,
                [("repo-a", "repo-a/worktree-2", "repo-a/submodule")],
            )
        finally:
            for event in release:
                event.set()
            bridge.deleteLater()
            app.processEvents()

    @staticmethod
    def _wait_until(app: QCoreApplication, predicate, timeout: float = 5.0) -> bool:
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
