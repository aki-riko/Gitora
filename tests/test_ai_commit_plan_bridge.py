# coding: utf-8
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from dataclasses import replace
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
    def __init__(
        self, single_first: bool = False, oversized_first: bool = False
    ):
        self.requests: list[PlannerRequest] = []
        self.single_first = single_first
        self.oversized_first = oversized_first

    @property
    def provider_id(self) -> str:
        return "plan-test"

    def generate_plan(self, request: PlannerRequest, cancel_event=None):
        self.requests.append(request)
        ids = list(request.snapshot.expected_ids(request.level))
        if self.single_first and len(self.requests) == 1 and len(ids) > 1:
            groups = [{
                "group_id": "group-1",
                "title": "feat: 合并改动",
                "body": "",
                "change_ids": ids,
                "depends_on": [],
                "rationale": "故意模拟模型首次未拆分",
                "warnings": [],
            }]
        elif self.oversized_first and len(self.requests) == 1 and len(ids) > 5:
            groups = [{
                "group_id": "group-1",
                "title": "feat: 核心改动",
                "body": "",
                "change_ids": ids[:1],
                "depends_on": [],
                "rationale": "故意模拟过大的提交组",
                "warnings": [],
            }, {
                "group_id": "group-2",
                "title": "feat: 其余改动",
                "body": "",
                "change_ids": ids[1:],
                "depends_on": [],
                "rationale": "故意模拟混合目的",
                "warnings": [],
            }]
        else:
            groups = []
            for index, change_id in enumerate(ids):
                groups.append({
                    "group_id": f"group-{index + 1}",
                    "title": f"feat: 规划改动 {index + 1}",
                    "body": "",
                    "change_ids": [change_id],
                    "depends_on": [],
                    "rationale": f"按 {request.level} 拆分",
                    "warnings": [],
                })
        return {
            "schema_version": "1",
            "snapshot_id": request.snapshot.snapshot_id,
            "level": request.level,
            "summary": f"真实工作区 {request.level} 计划",
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

    def test_plan_generation_includes_workspace_with_legacy_staged_setting(self) -> None:
        write_file(self.repo, "staged.py", "print('staged')\n")
        run_git(self.repo, "add", "staged.py")
        write_file(self.repo, "unstaged.py", "print('unstaged')\n")
        bridge = AiCommitPlanBridge(
            self.service,
            _Runtime(replace(self.settings, remote_scope="staged"), self.provider),
        )
        self.addCleanup(bridge.deleteLater)
        self.addCleanup(self.app.processEvents)
        prepared: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        self.assertEqual(prepared[0][2], 2)
        self.assertIn("未暂存和未跟踪", prepared[0][4])

    def test_single_group_model_response_is_retried_as_multi_commit_plan(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        self.provider = _PlanProvider(single_first=True)
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)

        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        self.assertEqual(len(self.provider.requests), 2)
        self.assertEqual(self.provider.requests[1].mode, "plan_retry")
        self.assertEqual(len(bridge.planModel.groups), 2)

    def test_oversized_model_group_is_retried_with_fixed_granularity(self) -> None:
        for index in range(7):
            write_file(self.repo, f"feature_{index}.py", f"value = {index}\n")
        self.provider = _PlanProvider(oversized_first=True)
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)

        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        self.assertEqual(len(self.provider.requests), 2)
        self.assertTrue(all(
            len(group["changes"]) <= 5 for group in bridge.planModel.groups
        ))

    def test_plan_generation_uses_requested_ui_language(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))

        bridge.preparePlanForLanguage("zh-CN")
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: bridge.planModel.hasPlan))

        self.assertEqual(self.provider.requests[0].output_language, "zh_CN")

    def test_accept_plan_commits_each_group_then_pushes_once(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        finished: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planCommitPushFinished.connect(lambda *args: finished.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: bridge.planModel.hasPlan))

        pushes: list[tuple] = []

        def fake_push(remote, branch, force=False, callback=None):
            pushes.append((remote, branch, force))
            if callback:
                callback(True, "推送成功")

        self.service.push = fake_push
        bridge.commitPlanAndPush()

        self.assertTrue(self.wait_until(lambda: len(finished) == 1))
        self.assertEqual(finished[0][0], True)
        self.assertIn("2 个 Commit", finished[0][1])
        self.assertEqual(len(pushes), 1)
        self.assertEqual(pushes[0][0], "origin")
        self.assertEqual(
            run_git(self.repo, "log", "-2", "--format=%s").stdout.splitlines(),
            ["feat: 规划改动 2", "feat: 规划改动 1"],
        )
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, "")

    def test_auto_commit_retries_transient_index_lock(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        finished: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planCommitPushFinished.connect(lambda *args: finished.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: bridge.planModel.hasPlan))

        lock_path = self.repo / ".git" / "index.lock"
        lock_path.write_bytes(b"")

        def release_lock() -> None:
            time.sleep(0.25)
            lock_path.unlink(missing_ok=True)

        threading.Thread(target=release_lock, daemon=True).start()
        pushes: list[tuple] = []

        def fake_push(remote, branch, force=False, callback=None):
            pushes.append((remote, branch, force))
            if callback:
                callback(True, "push ok")

        self.service.push = fake_push
        bridge.commitPlanAndPush()

        self.assertTrue(self.wait_until(lambda: len(finished) == 1))
        self.assertTrue(finished[0][0], finished[0][1])
        self.assertEqual(len(pushes), 1)
        self.assertEqual(
            run_git(self.repo, "log", "-1", "--format=%s").stdout.strip(),
            "feat: 规划改动 1",
        )

    def test_auto_commit_failure_restores_plan_without_snapshot_level_error(
        self,
    ) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        finished: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planCommitPushFinished.connect(lambda *args: finished.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: bridge.planModel.hasPlan))

        def fail_commit(_repo_path: str, _message: str) -> tuple[bool, str]:
            return False, "simulated commit failure"

        self.service.commit_at = fail_commit  # type: ignore[method-assign]
        bridge.commitPlanAndPush()

        self.assertTrue(self.wait_until(lambda: len(finished) == 1))
        self.assertFalse(finished[0][0])
        self.assertIn("simulated commit failure", finished[0][1])
        self.assertNotIn("AttributeError", finished[0][1])
        self.assertEqual(
            run_git(self.repo, "status", "--porcelain=v1").stdout,
            "?? one.py\n",
        )

    def test_push_failure_keeps_completed_local_commits(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        finished: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planCommitPushFinished.connect(lambda *args: finished.append(args))

        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: bridge.planModel.hasPlan))

        pushes: list[tuple] = []

        def fake_push(remote, branch, force=False, callback=None):
            pushes.append((remote, branch, force))
            if callback:
                callback(False, "远程拒绝推送")

        self.service.push = fake_push
        bridge.commitPlanAndPush()

        self.assertTrue(self.wait_until(lambda: len(finished) == 1))
        self.assertEqual(finished[0][0], False)
        self.assertIn("但推送失败", finished[0][1])
        self.assertEqual(len(pushes), 1)
        self.assertEqual(
            run_git(self.repo, "log", "-2", "--format=%s").stdout.splitlines(),
            ["feat: 规划改动 2", "feat: 规划改动 1"],
        )
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, "")

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

    def test_anthropic_plan_requires_explicit_consent(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        self.settings = self.settings.with_user_values({
            "provider": "anthropic",
            "remote_endpoint": "https://api.anthropic.com",
            "remote_model": "claude-sonnet-4-20250514",
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

    def test_non_loopback_ollama_plan_requires_explicit_consent(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        self.settings = self.settings.with_user_values({
            "local_endpoint": "http://192.168.1.20:11434",
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

    def test_repo_switch_before_plan_store_discards_old_context(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        other_repo = init_repo(Path(self.temp_dir.name) / "other-repo")
        write_file(other_repo, "other.txt", "other\n")
        commit_all(other_repo, "chore: other")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        original_store = bridge._request_state.store_prepared_if_current
        switched = False

        def switch_before_store(serial, repo, event, request):
            nonlocal switched
            if not switched:
                switched = True
                self.service.set_repo_path(str(other_repo), emit_status=False)
                bridge.invalidateRepo(str(other_repo))
            return original_store(serial, repo, event, request)

        bridge._request_state.store_prepared_if_current = switch_before_store
        bridge.preparePlan()

        self.assertTrue(self.wait_until(lambda: not bridge.busy))
        self.app.processEvents()
        self.assertEqual(prepared, [])
        self.assertIsNone(bridge._request_state.prepared)
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

    def test_hunk_plan_applies_and_advances_same_file_groups(self) -> None:
        lines = [f"line {index}\n" for index in range(1, 41)]
        write_file(self.repo, "code.py", "".join(lines))
        commit_all(self.repo, "chore: add hunk fixture")
        lines[1] = "changed top\n"
        lines[34] = "changed bottom\n"
        write_file(self.repo, "code.py", "".join(lines))
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        applied: list[tuple] = []
        advanced: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))
        bridge.groupApplied.connect(lambda *args: applied.append(args))
        bridge.planAdvanced.connect(lambda *args: advanced.append(args))

        bridge.prepareHunkPlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        self.assertEqual(prepared[0][2], 2)
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))

        self.assertEqual(self.provider.requests[-1].level, "hunk")
        self.assertEqual(bridge.planModel.level, "hunk")
        self.assertEqual(bridge.planModel.coverage["percent"], 100)
        self.assertEqual(len(bridge.planModel.groups), 2)
        self.assertEqual(
            {group["changes"][0]["path"] for group in bridge.planModel.groups},
            {"code.py"},
        )
        self.assertTrue(all(
            group["changes"][0]["kind"] == "hunk"
            for group in bridge.planModel.groups
        ))

        bridge.applyNextGroup()
        self.assertTrue(self.wait_until(lambda: len(applied) == 1))
        cached = run_git(self.repo, "diff", "--cached").stdout
        self.assertIn("changed top", cached)
        self.assertNotIn("changed bottom", cached)
        ok, message = self.service.commit(applied[0][1])
        self.assertTrue(ok, message)
        bridge.notifyCommitSucceeded()
        self.assertTrue(self.wait_until(lambda: len(advanced) == 1))
        self.assertFalse(advanced[0][0])
        self.assertEqual(len(bridge.planModel.groups), 1)

        bridge.applyNextGroup()
        self.assertTrue(self.wait_until(lambda: len(applied) == 2))
        ok, message = self.service.commit(applied[1][1])
        self.assertTrue(ok, message)
        bridge.notifyCommitSucceeded()
        self.assertTrue(self.wait_until(lambda: len(advanced) == 2))
        self.assertTrue(advanced[1][0])
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, "")

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

    def test_repo_switch_after_apply_restores_old_index_and_guard(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        other_repo = init_repo(Path(self.temp_dir.name) / "other-repo")
        write_file(other_repo, "other.txt", "other\n")
        commit_all(other_repo, "chore: other")
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        errors: list[str] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.planReady.connect(lambda *args: ready.append(args))
        bridge.errorOccurred.connect(errors.append)
        bridge.preparePlan()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        before_tree = run_git(self.repo, "write-tree").stdout.strip()
        original_current = bridge._is_current
        switched = False

        def switch_after_apply(serial, repo, event):
            nonlocal switched
            current = original_current(serial, repo, event)
            if current and not switched:
                switched = True
                self.service.set_repo_path(str(other_repo), emit_status=False)
                bridge.invalidateRepo(str(other_repo))
                return False
            return current

        bridge._is_current = switch_after_apply
        bridge.applyNextGroup()

        self.assertTrue(self.wait_until(
            lambda: not bridge.busy and not bridge._execution_guard
        ))
        self.assertEqual(run_git(self.repo, "write-tree").stdout.strip(), before_tree)
        self.assertEqual(run_git(self.repo, "diff", "--cached").stdout, "")
        self.assertTrue(any("已恢复" in message for message in errors))

    def test_repo_switch_while_awaiting_commit_restores_old_index(self) -> None:
        write_file(self.repo, "one.py", "print('one')\n")
        write_file(self.repo, "two.py", "print('two')\n")
        other_repo = init_repo(Path(self.temp_dir.name) / "awaiting-other-repo")
        write_file(other_repo, "other.txt", "other\n")
        commit_all(other_repo, "chore: other")
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
        before_tree = run_git(self.repo, "write-tree").stdout.strip()

        bridge.applyNextGroup()
        self.assertTrue(self.wait_until(lambda: len(applied) == 1))
        self.assertTrue(bridge.awaitingCommit)
        self.assertNotEqual(
            run_git(self.repo, "write-tree").stdout.strip(), before_tree
        )

        self.service.set_repo_path(str(other_repo), emit_status=False)
        bridge.invalidateRepo(str(other_repo))

        self.assertTrue(self.wait_until(lambda: not bridge._execution_guard))
        self.assertEqual(run_git(self.repo, "write-tree").stdout.strip(), before_tree)
        self.assertEqual(run_git(self.repo, "diff", "--cached").stdout, "")
        self.assertFalse(bridge.awaitingCommit)
        self.assertFalse(bridge.planModel.hasPlan)
        self.assertTrue(any("已恢复" in message for message in errors))

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
