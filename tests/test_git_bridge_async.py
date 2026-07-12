# coding: utf-8
from __future__ import annotations

import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication

from app_qml.backend.git_bridge import GitBridge


class GitBridgeAsyncTest(unittest.TestCase):
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
