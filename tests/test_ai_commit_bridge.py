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

from app.common.ai_commit_credentials import (
    CredentialStoreError,
    SystemCredentialStore,
)
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


class _ModelListProvider(_EchoProvider):
    def __init__(self, models: tuple[str, ...]):
        super().__init__()
        self.models = models

    def list_models(self) -> tuple[str, ...]:
        return self.models


class _MemoryCredentialBackend:
    def __init__(self):
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.values[(service, username)]


class _UnavailableCredentialStore:
    def get(self, _account: str) -> str:
        raise CredentialStoreError("系统凭据库读取失败")

    def set(self, _account: str, _secret: str) -> None:
        raise CredentialStoreError("系统凭据库保存失败")

    def delete(self, _account: str) -> bool:
        raise CredentialStoreError("系统凭据库删除失败")

    def has(self, account: str) -> bool:
        return bool(self.get(account))


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
        self.credential_backend = _MemoryCredentialBackend()

    def make_bridge(
        self,
        provider: str = "ollama",
        local_endpoint: str = "http://127.0.0.1:11434",
        remote_scope: str = "staged",
    ) -> AiCommitBridge:
        settings = self.store.load().with_user_values({
            "enabled": True,
            "provider": provider,
            "local_endpoint": local_endpoint,
            "local_model": "test-local",
            "remote_endpoint": "https://example.invalid/v1/responses",
            "remote_model": "test-remote",
            "remote_scope": remote_scope,
        })
        self.store.save(settings)
        bridge = AiCommitBridge(
            self.service,
            self.store,
            provider_factory=lambda _settings, _key: self.provider,
            credential_store=SystemCredentialStore(
                "Gitora.AiCommit.Test", self.credential_backend
            ),
        )
        self.addCleanup(bridge.deleteLater)
        self.addCleanup(self.app.processEvents)
        return bridge

    def stage_change(self) -> None:
        write_file(self.repo, "tracked.txt", "changed\n")
        run_git(self.repo, "add", "tracked.txt")

    def test_two_step_local_generation_only_fills_message(self) -> None:
        self.stage_change()
        write_file(self.repo, "extra.txt", "untracked\n")
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
        self.assertEqual(file_count, 2)
        self.assertGreater(character_count, 0)
        self.assertEqual(scope, "分析整个工作区的已暂存、未暂存和未跟踪改动")

        bridge.generatePrepared(request_id, False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        self.assertTrue(ready[0][2])
        self.assertEqual(ready[0][3], "fix: 更新真实文件")
        self.assertEqual(ready[0][4], "补充提交正文")
        self.assertEqual(len(self.provider.requests), 1)
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, before_status)
        self.assertEqual(run_git(self.repo, "rev-parse", "HEAD").stdout.strip(), before_head)

    def test_ai_submit_includes_workspace_when_legacy_scope_is_staged(self) -> None:
        write_file(self.repo, "tracked.txt", "changed but unstaged\n")
        bridge = self.make_bridge(remote_scope="staged")
        prepared: list[tuple] = []
        ready: list[tuple] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.commitMessageReady.connect(lambda *args: ready.append(args))

        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))
        self.assertEqual(
            prepared[0][4],
            "分析整个工作区的已暂存、未暂存和未跟踪改动",
        )

        bridge.generatePrepared(prepared[0][0], False)
        self.assertTrue(self.wait_until(lambda: len(ready) == 1))
        self.assertTrue(ready[0][2])
        self.assertEqual(len(self.provider.requests[0].snapshot.changes), 1)

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

    def test_non_loopback_ollama_requires_explicit_consent(self) -> None:
        self.stage_change()
        bridge = self.make_bridge(local_endpoint="http://192.168.1.20:11434")
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

    def test_system_key_is_persisted_outside_settings_and_deletable(self) -> None:
        bridge = self.make_bridge("openai_responses")
        result = bridge.storeApiKey("system-top-secret")

        self.assertTrue(result[0], result[1])
        self.assertTrue(bridge.hasStoredApiKey)
        self.assertNotIn(
            "system-top-secret", self.config_path.read_text(encoding="utf-8")
        )
        restarted = self.make_bridge("openai_responses")
        self.assertTrue(restarted.hasStoredApiKey)
        deleted = restarted.deleteStoredApiKey()
        self.assertTrue(deleted[0], deleted[1])
        self.assertFalse(restarted.hasStoredApiKey)

    def test_system_key_change_invalidates_prepared_remote_request(self) -> None:
        self.stage_change()
        bridge = self.make_bridge("openai_responses")
        prepared: list[tuple] = []
        errors: list[str] = []
        bridge.contextPrepared.connect(lambda *args: prepared.append(args))
        bridge.errorOccurred.connect(errors.append)
        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: len(prepared) == 1))

        result = bridge.storeApiKey("replacement-system-key")
        self.assertTrue(result[0], result[1])
        bridge.generatePrepared(prepared[0][0], True)

        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("已过期", errors[-1])
        self.assertEqual(self.provider.requests, [])

    def test_system_key_precedes_environment_and_is_scoped_to_endpoint(self) -> None:
        captured_keys: list[str] = []
        bridge = self.make_bridge("openai_responses")
        bridge._provider_factory = lambda _settings, key: (
            captured_keys.append(key) or self.provider
        )
        stored = bridge.storeApiKey("system-key")
        self.assertTrue(stored[0], stored[1])

        with patch.dict(os.environ, {"OPENAI_API_KEY": "environment-key"}):
            bridge.create_provider_for(bridge.planning_settings())
        self.assertEqual(captured_keys, ["system-key"])

        saved = bridge.saveSettings(
            True,
            "openai_responses",
            "",
            "",
            "https://other.example.invalid/v1/responses",
            "test-remote",
            "OPENAI_API_KEY",
            True,
            "staged",
        )
        self.assertTrue(saved[0], saved[1])
        self.assertFalse(bridge.hasStoredApiKey)

    def test_failed_native_read_marks_credential_store_unavailable(self) -> None:
        settings = self.store.load().with_user_values({
            "enabled": True,
            "provider": "openai_responses",
            "remote_endpoint": "https://example.invalid/v1/responses",
            "remote_model": "test-remote",
        })
        self.store.save(settings)
        bridge = AiCommitBridge(
            self.service,
            self.store,
            provider_factory=lambda _settings, _key: self.provider,
            credential_store=_UnavailableCredentialStore(),
        )
        self.addCleanup(bridge.deleteLater)

        self.assertFalse(bridge.credentialStoreAvailable)
        exposed = bridge.getSettings()
        self.assertFalse(exposed["credentialStoreAvailable"])
        self.assertEqual(exposed["credentialStoreError"], "系统凭据库读取失败")

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
            credential_store=SystemCredentialStore(
                "Gitora.AiCommit.Test", self.credential_backend
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

    def test_empty_workspace_returns_actionable_error(self) -> None:
        bridge = self.make_bridge()
        errors: list[str] = []
        bridge.errorOccurred.connect(errors.append)
        bridge.prepareCommitMessage()
        self.assertTrue(self.wait_until(lambda: bool(errors)))
        self.assertIn("工作区没有可生成提交信息的改动", errors[-1])

    def test_model_list_fetch_returns_sorted_unique_models(self) -> None:
        self.provider = _ModelListProvider(("model-z", "model-a", "model-z"))
        bridge = self.make_bridge()
        results: list[tuple] = []
        bridge.modelListFinished.connect(lambda *args: results.append(args))

        bridge.fetchModels()

        self.assertTrue(self.wait_until(lambda: len(results) == 1))
        provider_id, ok, models, message = results[0]
        self.assertEqual(provider_id, "ollama")
        self.assertTrue(ok)
        self.assertEqual(models, ["model-a", "model-z"])
        self.assertEqual(message, "已获取 2 个可用模型")
        self.assertFalse(bridge.busy)

    def test_model_list_fetch_reports_unsupported_provider(self) -> None:
        bridge = self.make_bridge()
        results: list[tuple] = []
        bridge.modelListFinished.connect(lambda *args: results.append(args))

        bridge.fetchModels()

        self.assertTrue(self.wait_until(lambda: len(results) == 1))
        self.assertFalse(results[0][1])
        self.assertIn("不支持获取模型列表", results[0][3])

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
