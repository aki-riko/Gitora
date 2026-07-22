# coding: utf-8
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from app.common.ai_commit_models import PlannerRequest
from app.common.ai_commit_provider import ModelProvider, ProviderCancelledError
from app.common.ai_commit_settings import AiCommitSettingsStore
from app.common.git_service import GitService
from app_qml.backend.ai_commit_bridge import AiCommitBridge
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class _EchoProvider(ModelProvider):
    def __init__(self):
        self.requests: list[PlannerRequest] = []

    @property
    def provider_id(self) -> str:
        return "echo"

    def generate_plan(self, request: PlannerRequest, cancel_event=None):
        self.requests.append(request)
        ids = list(request.snapshot.expected_ids(request.level))
        return {
            "schema_version": "1",
            "snapshot_id": request.snapshot.snapshot_id,
            "level": request.level,
            "summary": "根据真实暂存差异生成",
            "groups": [{
                "group_id": "main",
                "title": "fix: 更新真实文件",
                "body": "补充提交正文",
                "change_ids": ids,
                "depends_on": [],
                "rationale": "单一目的",
                "warnings": [],
            }],
            "unassigned_change_ids": [],
            "warnings": [],
        }


class _BlockingProvider(_EchoProvider):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()

    def generate_plan(self, request: PlannerRequest, cancel_event=None):
        self.requests.append(request)
        self.started.set()
        if cancel_event is None:
            raise AssertionError("取消测试必须传入 cancel_event")
        if not cancel_event.wait(timeout=5):
            raise AssertionError("取消信号未在超时前触发")
        raise ProviderCancelledError("请求已取消")


class AiCommitBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = init_repo(Path(self.temp_dir.name) / "repo")
        write_file(self.repo, "tracked.txt", "base\n")
        commit_all(self.repo, "chore: base")
        self.service = GitService()
        self.assertTrue(self.service.set_repo_path(str(self.repo), emit_status=False))
        self.config_path = Path(self.temp_dir.name) / "ai_commit.json"
        self.store = AiCommitSettingsStore(DEFAULTS, self.config_path)
        self.provider = _EchoProvider()

    def make_bridge(self, provider: str = "ollama") -> AiCommitBridge:
        settings = self.store.load().with_user_values({
            "enabled": True,
            "provider": provider,
            "local_endpoint": "http://127.0.0.1:11434",
            "local_model": "test-local",
            "remote_endpoint": "https://example.invalid/v1/responses",
            "remote_model": "test-remote",
        })
        self.store.save(settings)
        bridge = AiCommitBridge(
            self.service,
            self.store,
            provider_factory=lambda _settings, _key: self.provider,
        )
        self.addCleanup(bridge.deleteLater)
        self.addCleanup(self.app.processEvents)
        return bridge

    def stage_change(self) -> None:
        write_file(self.repo, "tracked.txt", "changed\n")
        run_git(self.repo, "add", "tracked.txt")

    def test_two_step_local_generation_only_fills_message(self) -> None:
        self.stage_change()
        before_status = run_git(self.repo, "status", "--porcelain=v1").stdout
        before_head = run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.commitMessageReady.connect(lambda *args: ready.append(args))

        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        request_id, is_remote, file_count, character_count, scope = prepared[0]
        self.assertFalse(is_remote)
        self.assertEqual(file_count, 1)
        self.assertGreater(character_count, 0)
        self.assertEqual(scope, "仅分析已暂存差异")

        bridge.generatePrepared(request_id, False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        self.assertTrue(ready[0][2])
        self.assertEqual(ready[0][3], "fix: 更新真实文件")
        self.assertEqual(ready[0][4], "补充提交正文")
        self.assertEqual(len(self.provider.requests), 1)
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, before_status)
        self.assertEqual(run_git(self.repo, "rev-parse", "HEAD").stdout.strip(), before_head)

    def test_remote_generation_requires_explicit_consent(self) -> None:
        self.stage_change()
        bridge = self.make_bridge("openai_responses")
        prepared: list[tuple] = []
        errors: list[str] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.errorOccurred.connect(errors.append)

        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        self.assertTrue(prepared[0][1])
        bridge.generatePrepared(prepared[0][0], False)

        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("未获得发送确认", errors[-1])
        self.assertEqual(self.provider.requests, [])

    def test_workspace_change_after_prepare_invalidates_generation(self) -> None:
        self.stage_change()
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.commitMessageReady.connect(lambda *args: ready.append(args))

        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        write_file(self.repo, "tracked.txt", "changed again\n")
        bridge.generatePrepared(prepared[0][0], False)

        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        self.assertFalse(ready[0][2])
        self.assertIn("工作区已变化", ready[0][5])
        self.assertEqual(self.provider.requests, [])

    def test_session_key_is_never_persisted(self) -> None:
        bridge = self.make_bridge("openai_responses")
        bridge.setSessionApiKey("session-top-secret")
        self.assertTrue(bridge.hasSessionApiKey)
        self.assertNotIn(
            "session-top-secret", self.config_path.read_text(encoding="utf-8")
        )
        bridge.clearSessionApiKey()
        self.assertFalse(bridge.hasSessionApiKey)

    def test_session_key_change_invalidates_prepared_remote_request(self) -> None:
        self.stage_change()
        bridge = self.make_bridge("openai_responses")
        prepared: list[tuple] = []
        errors: list[str] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.errorOccurred.connect(errors.append)
        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))

        bridge.setSessionApiKey("replacement-session-key")
        bridge.generatePrepared(prepared[0][0], True)

        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("已过期", errors[-1])
        self.assertEqual(self.provider.requests, [])

    def test_prepared_request_resolves_its_own_environment_key_name(self) -> None:
        self.stage_change()
        settings = self.store.load().with_user_values({
            "enabled": True,
            "provider": "openai_responses",
            "remote_endpoint": "https://example.invalid/v1/responses",
            "remote_model": "test-remote",
            "api_key_env": "GITORA_OLD_TEST_KEY",
        })
        self.store.save(settings)
        captured_keys: list[str] = []
        bridge = AiCommitBridge(
            self.service,
            self.store,
            provider_factory=lambda _settings, key: (
                captured_keys.append(key) or self.provider
            ),
        )
        self.addCleanup(bridge.deleteLater)
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.commitMessageReady.connect(lambda *args: ready.append(args))

        with patch.dict(os.environ, {
            "GITORA_OLD_TEST_KEY": "old-key",
            "GITORA_NEW_TEST_KEY": "new-key",
        }):
            bridge.prepareCommitMessage()
            self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
            captured_keys.clear()
            bridge._settings = settings.with_user_values({
                "api_key_env": "GITORA_NEW_TEST_KEY"
            })
            bridge.generatePrepared(prepared[0][0], True)
            self.assertTrue(self.wait_until(lambda: len(ready) == 1))

        self.assertEqual(captured_keys, ["old-key"])

    def test_cancelled_generation_discards_late_result_and_keeps_git_state(self) -> None:
        self.stage_change()
        before_status = run_git(self.repo, "status", "--porcelain=v1").stdout
        self.provider = _BlockingProvider()
        bridge = self.make_bridge()
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.commitMessageReady.connect(lambda *args: ready.append(args))

        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.provider.started.wait(timeout=5))
        bridge.cancelCurrent()

        self.assertTrue(self.wait_until(lambda: not bridge.busy))
        self.app.processEvents()
        self.assertEqual(ready, [])
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, before_status)

    def test_empty_staging_area_returns_actionable_error(self) -> None:
        bridge = self.make_bridge()
        errors: list[str] = []
        bridge.errorOccurred.connect(errors.append)
        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("暂存区为空", errors[-1])

    def test_repo_switch_before_prepared_store_discards_old_context(self) -> None:
        self.stage_change()
        other_repo = init_repo(Path(self.temp_dir.name) / "other-repo")
        write_file(other_repo, "other.txt", "other\n")
        commit_all(other_repo, "chore: other")
        bridge = self.make_bridge("openai_responses")
        prepared: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        original_store = bridge._store_prepared_if_current
        switched = False

        def switch_before_store(serial, repo, event, request):
            nonlocal switched
            if not switched:
                switched = True
                self.service.set_repo_path(str(other_repo), emit_status=False)
                bridge.invalidateRepo(str(other_repo))
            return original_store(serial, repo, event, request)

        bridge._store_prepared_if_current = switch_before_store
        bridge.prepareCommitMessage()

        self.assertTrue(self.wait_until(lambda: not bridge.busy))
        self.app.processEvents()
        self.assertEqual(prepared, [])
        self.assertIsNone(bridge._prepared)
        self.assertEqual(self.provider.requests, [])

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
