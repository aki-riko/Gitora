# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.ai_commit_models import ChangeSnapshot, PlannerRequest
from app.common.ai_commit_settings import AiCommitSettingsStore
from app_qml.backend.ai_commit_plan_request_state import (
    PlanRequestState,
    PreparedPlanRequest,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class PlanRequestStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = "repo-a"
        self.busy_changes = 0
        self.state = PlanRequestState(
            lambda: self.repo, self._record_busy_change
        )
        snapshot = ChangeSnapshot(
            "snapshot", "fingerprint", "repo-token", "head", "master",
            False, True, (),
        )
        request = PlannerRequest(snapshot, "plan", "file", True)
        settings = AiCommitSettingsStore(
            DEFAULTS, Path(self.temp_dir.name) / "ai_commit.json"
        ).load()
        self.prepared = PreparedPlanRequest(
            "request-1",
            self.repo,
            snapshot,
            request,
            settings,
            False,
        )

    def _record_busy_change(self) -> None:
        self.busy_changes += 1

    def test_prepared_request_is_stored_and_taken_once(self) -> None:
        serial, event = self.state.start(clear_prepared=True)

        self.assertTrue(
            self.state.store_prepared_if_current(
                serial, self.repo, event, self.prepared
            )
        )
        self.assertTrue(self.state.has_prepared)
        self.assertIsNone(self.state.take_prepared("wrong-request"))
        self.assertIs(self.state.take_prepared("request-1"), self.prepared)
        self.assertIsNone(self.state.take_prepared("request-1"))

    def test_repo_switch_rejects_prepared_request_atomically(self) -> None:
        serial, event = self.state.start(clear_prepared=True)
        self.repo = "repo-b"

        stored = self.state.store_prepared_if_current(
            serial, "repo-a", event, self.prepared
        )

        self.assertFalse(stored)
        self.assertFalse(self.state.has_prepared)

    def test_cancel_invalidates_event_and_clears_busy(self) -> None:
        serial, event = self.state.start(clear_prepared=True)
        self.assertTrue(self.state.busy)

        changed = self.state.cancel()

        self.assertTrue(changed)
        self.assertTrue(event.is_set())
        self.assertFalse(self.state.busy)
        self.assertFalse(self.state.is_serial_current(serial))
        self.assertEqual(self.busy_changes, 2)

    def test_stale_request_cannot_clear_new_request_busy_state(self) -> None:
        stale_serial, _ = self.state.start(clear_prepared=True)
        current_serial, _ = self.state.start(clear_prepared=True)

        self.assertFalse(self.state.set_busy_if_current(stale_serial, False))
        self.assertTrue(self.state.busy)
        self.assertTrue(self.state.set_busy_if_current(current_serial, False))
        self.assertFalse(self.state.busy)


if __name__ == "__main__":
    unittest.main()
