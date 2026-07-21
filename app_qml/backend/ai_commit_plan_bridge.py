# coding: utf-8
"""文件级 AI 提交规划的异步桥；本阶段只生成和编辑，不执行 Git 写入。"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Protocol

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.common.ai_commit_context import ChangeContextCollector, SnapshotCollectionError
from app.common.ai_commit_models import (
    ChangeSnapshot,
    CommitPlan,
    CommitPlanValidator,
    PlanProtocolError,
    PlannerRequest,
)
from app.common.ai_commit_provider import ModelProvider, ProviderCancelledError
from app.common.ai_commit_schema import build_user_input
from app.common.ai_commit_settings import AiCommitSettings, AiCommitSettingsError
from app.common.git_service import GitService
from app.common.logger import get_logger
from app_qml.backend.ai_commit_plan_model import AiCommitPlanModel


logger = get_logger("AiCommitPlanBridge")


class _PlannerRuntime(Protocol):
    def planning_settings(self) -> AiCommitSettings: ...

    def create_provider_for(self, settings: AiCommitSettings) -> ModelProvider: ...


@dataclass(frozen=True)
class _PreparedPlanRequest:
    request_id: str
    repo_path: str
    snapshot: ChangeSnapshot
    request: PlannerRequest
    settings: AiCommitSettings
    is_remote: bool


class AiCommitPlanBridge(QObject):
    """协调快照与模型；没有暂存、提交或推送接口。"""

    busyChanged = Signal()
    contextPrepared = Signal(str, bool, int, int, str)
    planReady = Signal(bool, str)
    errorOccurred = Signal(str)
    _resolved = Signal(int, str, object, object)

    def __init__(
        self,
        git_service: GitService,
        runtime: _PlannerRuntime,
        plan_model: AiCommitPlanModel | None = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._git = git_service
        self._runtime = runtime
        self._model = plan_model or AiCommitPlanModel(self)
        self._validator = CommitPlanValidator()
        self._busy = False
        self._serial = 0
        self._prepared: _PreparedPlanRequest | None = None
        self._cancel_event = threading.Event()
        self._state_lock = threading.Lock()
        self._resolved.connect(self._apply_resolved)

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(QObject, constant=True)
    def planModel(self) -> QObject:
        return self._model

    @Slot()
    def preparePlan(self) -> None:
        settings = self._runtime.planning_settings()
        if not settings.enabled:
            self.errorOccurred.emit("请先在设置中启用 AI 提交规划")
            return
        repo = self._git.repo_path or ""
        if not repo:
            self.errorOccurred.emit("请先打开一个 Git 仓库")
            return
        try:
            self._runtime.create_provider_for(settings)
        except (AiCommitSettingsError, RuntimeError, ValueError) as exc:
            self.errorOccurred.emit(str(exc))
            return

        serial, cancel_event = self._start_request(clear_prepared=True)
        include_unstaged = settings.remote_scope == "all"

        def work() -> None:
            try:
                snapshot = ChangeContextCollector(
                    self._git, settings.limits
                ).collect(repo, include_unstaged=include_unstaged)
                if not snapshot.changes:
                    scope = "工作区" if include_unstaged else "暂存区"
                    raise SnapshotCollectionError(f"{scope}没有可规划的改动")
                request = PlannerRequest(snapshot, "plan", "file", settings.generate_body)
                request_id = f"plan-{serial}-{snapshot.snapshot_id[:16]}"
                prepared = _PreparedPlanRequest(
                    request_id,
                    repo,
                    snapshot,
                    request,
                    settings,
                    settings.provider == "openai_responses",
                )
                if not self._is_current(serial, repo, cancel_event):
                    return
                with self._state_lock:
                    self._prepared = prepared
                scope_summary = (
                    "分析已暂存、未暂存和未跟踪改动"
                    if include_unstaged else "仅分析已暂存差异"
                )
                self.contextPrepared.emit(
                    request_id,
                    prepared.is_remote,
                    len(snapshot.changes),
                    len(build_user_input(request)),
                    scope_summary,
                )
            except (SnapshotCollectionError, AiCommitSettingsError) as exc:
                logger.warning(f"准备文件级规划失败: {type(exc).__name__}")
                self._emit_error_if_current(serial, str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"准备文件级规划异常: {type(exc).__name__}")
                self._emit_error_if_current(serial, "准备文件级规划上下文失败")
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
            self.errorOccurred.emit("规划请求已过期，请重新生成")
            return
        if prepared.is_remote and not remote_consent:
            self.errorOccurred.emit("远程规划未获得发送确认")
            return

        serial, cancel_event = self._start_request(clear_prepared=False)

        def work() -> None:
            try:
                collector = ChangeContextCollector(self._git, prepared.settings.limits)
                self._ensure_fingerprint(collector, prepared)
                provider = self._runtime.create_provider_for(prepared.settings)
                raw_plan = provider.generate_plan(prepared.request, cancel_event)
                plan = CommitPlan.from_mapping(raw_plan)
                result = self._validator.validate(
                    plan,
                    prepared.snapshot,
                    expected_level=prepared.request.level,
                )
                if not result.valid:
                    details = "；".join(issue.message for issue in result.issues)
                    raise PlanProtocolError(details or "模型计划校验失败")
                self._ensure_fingerprint(collector, prepared)
                if not self._is_current(serial, prepared.repo_path, cancel_event):
                    return
                self._resolved.emit(
                    serial, prepared.repo_path, plan, prepared.snapshot
                )
            except ProviderCancelledError:
                return
            except (
                AiCommitSettingsError,
                PlanProtocolError,
                SnapshotCollectionError,
                RuntimeError,
                ValueError,
            ) as exc:
                logger.warning(f"生成文件级规划失败: {type(exc).__name__}")
                self._emit_error_if_current(serial, str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"生成文件级规划异常: {type(exc).__name__}")
                self._emit_error_if_current(serial, "生成文件级规划失败")
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
        self._cancel_request()

    @Slot()
    def invalidateWorkspace(self) -> None:
        self._cancel_request()
        self._model.markStale()

    @Slot(str)
    def invalidateRepo(self, _path: str) -> None:
        self._cancel_request()
        self._model.clear()

    @Slot()
    def clearPlan(self) -> None:
        self._model.clear()

    @Slot(int, str, object, object)
    def _apply_resolved(
        self,
        serial: int,
        repo: str,
        plan: CommitPlan,
        snapshot: ChangeSnapshot,
    ) -> None:
        with self._state_lock:
            current = serial == self._serial and not self._cancel_event.is_set()
        if not current or repo != (self._git.repo_path or ""):
            return
        self._model.load(plan, snapshot)
        self.planReady.emit(True, plan.summary or "文件级提交计划已生成")

    @staticmethod
    def _ensure_fingerprint(
        collector: ChangeContextCollector,
        prepared: _PreparedPlanRequest,
    ) -> None:
        current = collector.workspace_fingerprint(prepared.repo_path)
        if current != prepared.snapshot.workspace_fingerprint:
            raise SnapshotCollectionError("工作区已变化，请重新规划")

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

    def _cancel_request(self) -> None:
        with self._state_lock:
            self._serial += 1
            self._cancel_event.set()
            self._cancel_event = threading.Event()
            self._prepared = None
            was_busy = self._busy
            self._busy = False
        if was_busy:
            self.busyChanged.emit()

    def _set_busy_if_current(self, serial: int, value: bool) -> None:
        with self._state_lock:
            if serial != self._serial or self._busy == value:
                return
            self._busy = value
        self.busyChanged.emit()

    def _is_current(
        self, serial: int, repo: str, event: threading.Event
    ) -> bool:
        with self._state_lock:
            current = serial == self._serial and not event.is_set()
        return current and repo == (self._git.repo_path or "")

    def _emit_error_if_current(self, serial: int, message: str) -> None:
        with self._state_lock:
            current = serial == self._serial and not self._cancel_event.is_set()
        if current:
            self.errorOccurred.emit(message)
