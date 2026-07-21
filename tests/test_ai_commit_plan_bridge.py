# coding: utf-8
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.common.ai_commit_models import PlannerRequest
from app.common.ai_commit_provider import ModelProvider
from app.common.ai_commit_settings import AiCommitSettings, AiCommitSettingsStore
from app.common.git_service import GitService
from app_qml.backend.ai_commit_plan_bridge import AiCommitPlanBridge
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class _PlanProvider(ModelProvider):
    def __init__(self):
        self.requests: list[PlannerRequest] = []

    @property
    def provider_id(self) -> str:
        return "plan-test"

    def generate_plan(self, request: PlannerRequest, cancel_event=None):
        self.requests.append(request)
        ids = list(request.snapshot.expected_ids("file"))
        groups = []
        for index, change_id in enumerate(ids):
            groups.append({
                "group_id": f"group-{index + 1}",
                "title": f"feat: 规划改动 {index + 1}",
                "body": "",
                "change_ids": [change_id],
                "depends_on": [],
                "rationale": "按文件拆分",
                "warnings": [],
            })
        return {
            "schema_version": "1",
            "snapshot_id": request.snapshot.snapshot_id,
            "level": "file",
            "summary": "真实工作区文件级计划",
            "groups": groups,
            "unassigned_change_ids": [],
            "warnings": [],
        }


class _Runtime:
    def __init__(self, settings: AiCommitSettings, provider: ModelProvider):
        self.settings = settings
        self.provider = provider

    def planning_settings(self) -> AiCommitSettings:
        return self.settings

    def create_provider_for(self, settings: AiCommitSettings) -> ModelProvider:
        self.assert_same_settings = settings == self.settings
        return self.provider


class AiCommitPlanBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = init_repo(Path(self.temp_dir.name) / "repo")
        write_file(self.repo, "base.txt", "base\n")
        commit_all(self.repo, "chore: base")
        self.service = GitService()
        self.assertTrue(self.service.set_repo_path(str(self.repo), emit_status=False))
        store = AiCommitSettingsStore(
            DEFAULTS, Path(self.temp_dir.name) / "ai_commit.json"
        )
        self.provider = _PlanProvider()
        self.settings = store.load().with_user_values({
            "enabled": True,
            "provider": "ollama",
            "local_endpoint": "http://127.0.0.1:11434",
            "local_model": "test-local",
            "remote_scope": "all",
        })

    def make_bridge(self) -> AiCommitPlanBridge:
        bridge = AiCommitPlanBridge(
            self.service, _Runtime(self.settings, self.provider)
        )
        self.addCleanup(bridge.deleteLater)
        self.addCleanup(self.app.processEvents)
        return bridge

    def test_plan_generation_uses_real_workspace_without_git_writes(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        before_status = run_git(self.repo, "status", "--porcelain=v1").stdout
        before_head = run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        self.assertFalse(prepared[0][1])
        self.assertEqual(prepared[0][2], 2)
        self.assertIn("未暂存", prepared[0][4])
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))

        model = bridge.planModel
        self.assertTrue(model.hasPlan)
        self.assertEqual(len(model.groups), 2)
        self.assertEqual(len(self.provider.requests), 1)
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, before_status)
        self.assertEqual(run_git(self.repo, "rev-parse", "HEAD").stdout.strip(), before_head)

    def test_remote_plan_requires_explicit_consent(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        self.settings = self.settings.with_user_values({
            "provider": "openai_responses",
            "remote_endpoint": "https://example.invalid/v1/responses",
            "remote_model": "test-remote",
        })
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        errors: list[str] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.errorOccurred.connect(errors.append)

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        self.assertTrue(prepared[0][1])
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("未获得发送确认", errors[-1])
        self.assertEqual(self.provider.requests, [])

    def test_workspace_invalidation_keeps_plan_visible_but_stale(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))
        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))

        write_file(self.repo, "one.py", "print('changed again')\n")
        bridge.invalidateWorkspace()
        self.assertTrue(bridge.planModel.hasPlan)
        self.assertTrue(self.wait_until(lambda: bridge.planModel.stale))
        self.assertFalse(bridge.planModel.executable)

    def test_apply_commit_and_continue_all_groups_without_auto_commit(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        applied: list[tuple] = []
        advanced: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))
        bridge.groupApplied.connect(lambda *args: applied.append(args))
        bridge.planAdvanced.connect(lambda *args: advanced.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        first_path = bridge.planModel.groups[0]["changes"][0]["path"]

        bridge.applyNextGroup()
        self.assertTrue(self.wait_until(lambda: len(applied) == 1))
        self.assertTrue(bridge.awaitingCommit)
        self.assertEqual(
            run_git(self.repo, "diff", "--cached", "--name-only").stdout.strip(),
            first_path,
        )
        head_before = run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(run_git(self.repo, "rev-parse", "HEAD").stdout.strip(), head_before)

        ok, _message = self.service.commit(applied[0][1])
        self.assertTrue(ok)
        bridge.notifyCommitSucceeded()
        self.assertTrue(self.wait_until(lambda: len(advanced) == 1))
        self.assertFalse(advanced[0][0])
        self.assertFalse(bridge.awaitingCommit)
        self.assertEqual(len(bridge.planModel.groups), 1)
        self.assertFalse(bridge.planModel.stale)

        bridge.applyNextGroup()
        self.assertTrue(self.wait_until(lambda: len(applied) == 2))
        ok, _message = self.service.commit(applied[1][1])
        self.assertTrue(ok)
        bridge.notifyCommitSucceeded()
        self.assertTrue(self.wait_until(lambda: len(advanced) == 2))
        self.assertTrue(advanced[1][0])
        self.assertFalse(bridge.planModel.hasPlan)
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, "")

    def test_remaining_file_edit_after_apply_invalidates_followup_plan(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        applied: list[tuple] = []
        errors: list[str] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))
        bridge.groupApplied.connect(lambda *args: applied.append(args))
        bridge.errorOccurred.connect(errors.append)
        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        remaining_path = bridge.planModel.groups[1]["changes"][0]["path"]

        bridge.applyNextGroup()
        self.assertTrue(self.wait_until(lambda: len(applied) == 1))
        write_file(self.repo, remaining_path, "changed while first group awaited commit\n")
        ok, _message = self.service.commit(applied[0][1])
        self.assertTrue(ok)
        bridge.notifyCommitSucceeded()

        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("发生变化", errors[-1])
        self.assertTrue(bridge.planModel.stale)
        self.assertFalse(bridge.planModel.executable)

    def test_final_group_does_not_hide_new_unstaged_edit(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        applied: list[tuple] = []
        errors: list[str] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))
        bridge.groupApplied.connect(lambda *args: applied.append(args))
        bridge.errorOccurred.connect(errors.append)
        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        bridge.applyNextGroup()
        self.assertTrue(self.wait_until(lambda: len(applied) == 1))

        write_file(self.repo, "one.py", "edited after staging\n")
        ok, _message = self.service.commit(applied[0][1])
        self.assertTrue(ok)
        bridge.notifyCommitSucceeded()

        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("仍有新改动", errors[-1])
        self.assertTrue(bridge.planModel.stale)

    def wait_until(self, predicate, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.01)
        self.app.processEvents()
        return bool(predicate())


if __name__ == "__main__":
    unittest.main()
