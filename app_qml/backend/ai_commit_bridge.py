# coding: utf-8
"""AI 提交规划器与 QML 之间的异步、安全确认桥。"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.common.ai_commit_connection import (
    AiCommitCredentialService,
    ProviderFactory,
    create_model_provider,
)
from app.common.ai_commit_credentials import CredentialStore
from app.common.ai_commit_context import (
    ChangeContextCollector,
    SnapshotCollectionError,
)
from app.common.ai_commit_http import (
    endpoint_requires_remote_consent,
    HttpProviderError,
    OllamaProvider,
)
from app.common.ai_commit_models import (
    ChangeSnapshot,
    CommitPlan,
    CommitPlanValidator,
    PlanProtocolError,
    PlannerRequest,
)
from app.common.ai_commit_provider import ModelProvider, ProviderCancelledError
from app.common.ai_commit_schema import build_user_input
from app.common.ai_commit_settings import (
    AiCommitSettings,
    AiCommitSettingsError,
    AiCommitSettingsStore,
)
from app.common.git_service import GitService
from app.common.logger import get_logger


logger = get_logger("AiCommitBridge")


@dataclass(frozen=True)
class _PreparedRequest:
    request_id: str
    repo_path: str
    snapshot: ChangeSnapshot
    request: PlannerRequest
    settings: AiCommitSettings
    is_remote: bool


class AiCommitBridge(QObject):
    """模型只生成候选信息；本桥不提供任何 Git 写操作。"""

    settingsChanged = Signal()
    busyChanged = Signal()
    contextPrepared = Signal(str, bool, int, int, str)
    commitMessageReady = Signal(str, str, bool, str, str, str)
    connectionTestFinished = Signal(bool, str)
    modelListFinished = Signal(str, bool, "QVariantList", str)
    errorOccurred = Signal(str)

    def __init__(
        self,
        git_service: GitService,
        settings_store: AiCommitSettingsStore | None = None,
        provider_factory: ProviderFactory | None = None,
        credential_store: CredentialStore | None = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._git = git_service
        self._store = settings_store or AiCommitSettingsStore()
        self._settings = self._store.load()
        self._provider_factory = provider_factory or create_model_provider
        self._credentials = AiCommitCredentialService(
            self._settings.credential_service, credential_store
        )
        self._validator = CommitPlanValidator()
        self._busy = False
        self._serial = 0
        self._prepared: _PreparedRequest | None = None
        self._cancel_event = threading.Event()
        self._state_lock = threading.Lock()
        self._credentials.refresh(self._settings)

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=settingsChanged)
    def featureEnabled(self) -> bool:
        return self._settings.enabled

    @Property(bool, notify=settingsChanged)
    def hasStoredApiKey(self) -> bool:
        return self._credentials.has_stored_api_key

    @Property(bool, notify=settingsChanged)
    def credentialStoreAvailable(self) -> bool:
        return self._credentials.available

    @Slot(result="QVariantMap")
    def getSettings(self) -> dict:
        settings = self._settings
        return {
            "enabled": settings.enabled,
            "provider": settings.provider,
            "localEndpoint": settings.local_endpoint,
            "localModel": settings.local_model,
            "remoteEndpoint": settings.remote_endpoint,
            "remoteModel": settings.remote_model,
            "apiKeyEnv": settings.api_key_env,
            "generateBody": settings.generate_body,
            "remoteScope": settings.remote_scope,
            "hasStoredApiKey": self._credentials.has_stored_api_key,
            "credentialStoreAvailable": self.credentialStoreAvailable,
            "credentialStoreError": self._credentials.error,
            "hasEnvironmentApiKey": self._credentials.has_environment_api_key(
                settings
            ),
        }

    @Slot(bool, str, str, str, str, str, str, bool, str, result="QVariantList")
    def saveSettings(
        self,
        enabled: bool,
        provider: str,
        local_endpoint: str,
        local_model: str,
        remote_endpoint: str,
        remote_model: str,
        api_key_env: str,
        generate_body: bool,
        remote_scope: str,
    ) -> list:
        try:
            updated = self._settings.with_user_values({
                "enabled": enabled,
                "provider": provider,
                "local_endpoint": local_endpoint,
                "local_model": local_model,
                "remote_endpoint": remote_endpoint,
                "remote_model": remote_model,
                "api_key_env": api_key_env,
                "generate_body": generate_body,
                "remote_scope": remote_scope,
            })
            self._store.save(updated)
        except (AiCommitSettingsError, OSError) as exc:
            logger.warning(f"保存 AI 配置失败: {type(exc).__name__}")
            return [False, str(exc)]
        self._settings = updated
        self.invalidateWorkspace()
        self._credentials.refresh(self._settings)
        self.settingsChanged.emit()
        return [True, "AI 提交规划设置已保存"]

    @Slot(str, result="QVariantList")
    def storeApiKey(self, value: str) -> list:
        self.invalidateWorkspace()
        result = self._credentials.store_api_key(self._settings, value)
        self.settingsChanged.emit()
        return list(result)

    @Slot(result="QVariantList")
    def deleteStoredApiKey(self) -> list:
        self.invalidateWorkspace()
        result = self._credentials.delete_stored_api_key(self._settings)
        self.settingsChanged.emit()
        return list(result)

    def planning_settings(self) -> AiCommitSettings:
        """供同进程文件级规划桥读取当前不可变配置快照。"""
        return self._settings

    def create_provider_for(self, settings: AiCommitSettings) -> ModelProvider:
        """复用同一提供方工厂和已解析凭据，不把密钥暴露给 QML。"""
        return self._provider_factory(
            settings, self._credentials.resolve_api_key(settings)
        )

    @Slot()
    def prepareCommitMessage(self) -> None:
        if not self._settings.enabled:
            self.errorOccurred.emit("请先在设置中启用 AI 提交规划")
            return
        repo = self._git.repo_path or ""
        if not repo:
            self.errorOccurred.emit("请先打开一个 Git 仓库")
            return
        try:
            self._provider_factory(
                self._settings, self._credentials.resolve_api_key(self._settings)
            )
        except (HttpProviderError, AiCommitSettingsError) as exc:
            self.errorOccurred.emit(str(exc))
            return

        serial, cancel_event = self._start_request(clear_prepared=True)
        settings = self._settings

        def work() -> None:
            try:
                snapshot = ChangeContextCollector(
                    self._git, settings.limits
                ).collect(repo, include_unstaged=False)
                if not snapshot.changes:
                    raise SnapshotCollectionError("暂存区为空，请先暂存改动")
                if not snapshot.complete:
                    raise SnapshotCollectionError(
                        "已暂存差异超过配置上限，无法生成可靠的提交信息"
                    )
                request = PlannerRequest(
                    snapshot, "message", "file", settings.generate_body
                )
                request_id = f"{serial}-{snapshot.snapshot_id[:16]}"
                prepared = _PreparedRequest(
                    request_id, repo, snapshot, request, settings,
                    settings.provider == "openai_responses"
                    or endpoint_requires_remote_consent(settings.local_endpoint),
                )
                if not self._store_prepared_if_current(
                    serial, repo, cancel_event, prepared
                ):
                    return
                character_count = len(build_user_input(request))
                self.contextPrepared.emit(
                    request_id,
                    prepared.is_remote,
                    len(snapshot.changes),
                    character_count,
                    "仅分析已暂存差异",
                )
            except (SnapshotCollectionError, AiCommitSettingsError) as exc:
                logger.warning(f"准备 AI 提交上下文失败: {type(exc).__name__}")
                self._emit_error_if_current(serial, str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"准备 AI 提交上下文异常: {type(exc).__name__}")
                self._emit_error_if_current(serial, "准备提交上下文失败")
            finally:
                self._set_busy_if_current(serial, False)

        threading.Thread(target=work, daemon=True).start()

    @Slot(str, bool)
    def generatePrepared(self, request_id: str, remote_consent: bool) -> None:
        with self._state_lock:
            prepared = self._prepared
            if prepared is None or prepared.request_id != request_id:
                prepared = None
            else:
                self._prepared = None
        if prepared is None:
            self.errorOccurred.emit("AI 请求已过期，请重新生成")
            return
        if prepared.is_remote and not remote_consent:
            self.errorOccurred.emit("远程模型调用未获得发送确认")
            return

        serial, cancel_event = self._start_request(clear_prepared=False)

        def work() -> None:
            try:
                collector = ChangeContextCollector(self._git, prepared.settings.limits)
                if collector.workspace_fingerprint(prepared.repo_path) != prepared.snapshot.workspace_fingerprint:
                    raise SnapshotCollectionError("工作区已变化，请重新生成")
                provider = self._provider_factory(
                    prepared.settings,
                    self._credentials.resolve_api_key(prepared.settings),
                )
                raw_plan = provider.generate_plan(prepared.request, cancel_event)
                plan = CommitPlan.from_mapping(raw_plan)
                result = self._validator.validate(
                    plan, prepared.snapshot, expected_level=prepared.request.level
                )
                if not result.valid:
                    details = "；".join(issue.message for issue in result.issues)
                    raise PlanProtocolError(details or "模型计划校验失败")
                if len(plan.groups) != 1:
                    raise PlanProtocolError("单条提交信息模式必须只返回一个提交组")
                if collector.workspace_fingerprint(prepared.repo_path) != prepared.snapshot.workspace_fingerprint:
                    raise SnapshotCollectionError("模型返回前工作区已变化，请重新生成")
                if not self._is_current(serial, prepared.repo_path, cancel_event):
                    return
                group = plan.groups[0]
                body = group.body if prepared.settings.generate_body else ""
                self.commitMessageReady.emit(
                    prepared.repo_path, prepared.request_id, True,
                    group.title.strip(), body.strip(), plan.summary,
                )
            except ProviderCancelledError:
                return
            except (
                HttpProviderError, PlanProtocolError,
                SnapshotCollectionError, AiCommitSettingsError,
            ) as exc:
                logger.warning(f"生成 AI 提交信息失败: {type(exc).__name__}")
                self._emit_message_error_if_current(
                    serial, prepared.repo_path, prepared.request_id, str(exc)
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"生成 AI 提交信息异常: {type(exc).__name__}")
                self._emit_message_error_if_current(
                    serial, prepared.repo_path, prepared.request_id,
                    "生成提交信息失败",
                )
            finally:
                self._set_busy_if_current(serial, False)

        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def cancelPrepared(self, request_id: str) -> None:
        with self._state_lock:
            if self._prepared and self._prepared.request_id == request_id:
                self._prepared = None

    @Slot()
    def cancelCurrent(self) -> None:
        self.invalidateWorkspace()

    @Slot()
    def testConnection(self) -> None:
        if self._busy:
            self.errorOccurred.emit("已有 AI 操作正在进行")
            return
        settings = self._settings
        serial, cancel_event = self._start_request(clear_prepared=False)

        def work() -> None:
            try:
                provider = self._provider_factory(
                    settings, self._credentials.resolve_api_key(settings)
                )
                if isinstance(provider, OllamaProvider):
                    models = provider.list_models()
                    if settings.local_model and settings.local_model not in models:
                        raise HttpProviderError("连接成功，但未找到配置的本地模型")
                    message = f"连接成功，检测到 {len(models)} 个本地模型"
                else:
                    message = "远程配置格式有效，将在首次生成时验证连接"
                if self._is_current(serial, self._git.repo_path or "", cancel_event, check_repo=False):
                    self.connectionTestFinished.emit(True, message)
            except (HttpProviderError, AiCommitSettingsError) as exc:
                logger.warning(f"检测 AI 连接失败: {type(exc).__name__}")
                if self._is_serial_current(serial, cancel_event):
                    self.connectionTestFinished.emit(False, str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"检测 AI 连接异常: {type(exc).__name__}")
                if self._is_serial_current(serial, cancel_event):
                    self.connectionTestFinished.emit(False, "模型连接检测失败")
            finally:
                self._set_busy_if_current(serial, False)

        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def fetchModels(self) -> None:
        if self._busy:
            self.errorOccurred.emit("已有 AI 操作正在进行")
            return
        settings = self._settings
        provider_id = settings.provider
        serial, cancel_event = self._start_request(clear_prepared=False)

        def work() -> None:
            try:
                provider = self._provider_factory(
                    settings, self._credentials.resolve_api_key(settings)
                )
                try:
                    models = provider.list_models()
                except NotImplementedError as exc:
                    raise HttpProviderError("当前模型提供方不支持获取模型列表") from exc
                available = sorted(set(models), key=str.casefold)
                if not available:
                    raise HttpProviderError("模型服务未返回可用模型")
                message = f"已获取 {len(available)} 个可用模型"
                if self._is_serial_current(serial, cancel_event):
                    self.modelListFinished.emit(
                        provider_id, True, available, message
                    )
            except (HttpProviderError, AiCommitSettingsError) as exc:
                logger.warning(f"获取 AI 模型列表失败: {type(exc).__name__}")
                if self._is_serial_current(serial, cancel_event):
                    self.modelListFinished.emit(provider_id, False, [], str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"获取 AI 模型列表异常: {type(exc).__name__}")
                if self._is_serial_current(serial, cancel_event):
                    self.modelListFinished.emit(
                        provider_id, False, [], "获取模型列表失败"
                    )
            finally:
                self._set_busy_if_current(serial, False)

        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def invalidateWorkspace(self) -> None:
        with self._state_lock:
            self._serial += 1
            self._cancel_event.set()
            self._cancel_event = threading.Event()
            self._prepared = None
            was_busy = self._busy
            self._busy = False
        if was_busy:
            self.busyChanged.emit()

    @Slot(str)
    def invalidateRepo(self, _path: str) -> None:
        self.invalidateWorkspace()

    def _start_request(self, clear_prepared: bool) -> tuple[int, threading.Event]:
        with self._state_lock:
            self._serial += 1
            self._cancel_event.set()
            self._cancel_event = threading.Event()
            if clear_prepared:
                self._prepared = None
            self._busy = True
            serial = self._serial
            event = self._cancel_event
        self.busyChanged.emit()
        return serial, event

    def _set_busy_if_current(self, serial: int, value: bool) -> None:
        with self._state_lock:
            if serial != self._serial or self._busy == value:
                return
            self._busy = value
        self.busyChanged.emit()

    def _is_serial_current(self, serial: int, event: threading.Event) -> bool:
        with self._state_lock:
            return serial == self._serial and not event.is_set()

    def _is_current(
        self,
        serial: int,
        repo: str,
        event: threading.Event,
        check_repo: bool = True,
    ) -> bool:
        if not self._is_serial_current(serial, event):
            return False
        return not check_repo or repo == (self._git.repo_path or "")

    def _store_prepared_if_current(
        self,
        serial: int,
        repo: str,
        event: threading.Event,
        prepared: _PreparedRequest,
    ) -> bool:
        with self._state_lock:
            if (
                serial != self._serial
                or event.is_set()
                or repo != (self._git.repo_path or "")
            ):
                return False
            self._prepared = prepared
            return True

    def _emit_error_if_current(self, serial: int, message: str) -> None:
        with self._state_lock:
            current = serial == self._serial and not self._cancel_event.is_set()
        if current:
            self.errorOccurred.emit(message)

    def _emit_message_error_if_current(
        self, serial: int, repo: str, request_id: str, message: str
    ) -> None:
        with self._state_lock:
            current = serial == self._serial and not self._cancel_event.is_set()
        if current:
            self.commitMessageReady.emit(repo, request_id, False, "", "", message)
