# coding: utf-8
"""文件级与代码块级 AI 提交规划异步桥。"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional, Protocol

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.common.ai_commit_context import ChangeContextCollector, SnapshotCollectionError
from app.common.ai_commit_executor import (
    AppliedFileGroup,
    FilePlanExecutor,
    HunkPlanExecutor,
    PlanExecutionError,
)
from app.common.ai_commit_models import (
    ChangeSnapshot, CommitPlan, CommitPlanValidator, PlanProtocolError,
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
    awaitingCommitChanged = Signal()
    contextPrepared = Signal(str, bool, int, int, str)
    planReady = Signal(bool, str)
    groupApplied = Signal(str, str, str, str)
    planAdvanced = Signal(bool, str)
    errorOccurred = Signal(str)
    _resolved = Signal(int, str, object, object)
    _applyFinished = Signal(int, object)
    _commitChecked = Signal(int, bool, str, object)
    _workspaceChecked = Signal(str, str, str)

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
        self._executor = FilePlanExecutor(git_service)
        self._hunk_executor = HunkPlanExecutor(git_service)
        self._busy = False
        self._awaiting_commit = False
        self._execution_guard = False
        self._applied: AppliedFileGroup | None = None
        self._serial = 0
        self._prepared: _PreparedPlanRequest | None = None
        self._cancel_event = threading.Event()
        self._state_lock = threading.Lock()
        self._resolved.connect(self._apply_resolved)
        self._applyFinished.connect(self._apply_finished)
        self._commitChecked.connect(self._commit_checked)
        self._workspaceChecked.connect(self._workspace_checked)

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(bool, notify=awaitingCommitChanged)
    def awaitingCommit(self) -> bool:
        return self._awaiting_commit

    @Property(QObject, constant=True)
    def planModel(self) -> QObject:
        return self._model

    @Slot()
    def preparePlan(self) -> None:
        self._prepare_plan("file")

    @Slot()
    def prepareHunkPlan(self) -> None:
        self._prepare_plan("hunk")

    def _prepare_plan(self, level: str) -> None:
        if self._awaiting_commit:
            self.errorOccurred.emit("请先提交已应用的计划组")
            return
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
                request = PlannerRequest(snapshot, "plan", level, settings.generate_body)
                request_id = f"plan-{level}-{serial}-{snapshot.snapshot_id[:16]}"
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
                    len(snapshot.expected_ids(level)),
                    len(build_user_input(request)),
                    scope_summary,
                )
            except (SnapshotCollectionError, AiCommitSettingsError) as exc:
                logger.warning(f"准备 {level} 规划失败: {type(exc).__name__}")
                self._emit_error_if_current(serial, str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"准备 {level} 规划异常: {type(exc).__name__}")
                self._emit_error_if_current(serial, "准备提交规划上下文失败")
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
        if self._execution_guard:
            self.errorOccurred.emit("暂存执行不能中途取消，请等待完成")
            return
        self._cancel_request()

    @Slot()
    def invalidateWorkspace(self) -> None:
        if self._execution_guard or self._awaiting_commit:
            return
        if self._busy:
            self._cancel_request()
            self._model.markStale()
            return
        snapshot = self._model.snapshot()
        if snapshot is None:
            with self._state_lock:
                has_prepared = self._prepared is not None
            if has_prepared:
                self._cancel_request()
            return
        settings = self._runtime.planning_settings()
        repo = self._git.repo_path or ""
        expected = snapshot.workspace_fingerprint

        def work() -> None:
            try:
                current = ChangeContextCollector(
                    self._git, settings.limits
                ).workspace_fingerprint(repo)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"复验规划工作区失败: {type(exc).__name__}")
                current = ""
            self._workspaceChecked.emit(repo, expected, current)

        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def invalidateRepo(self, _path: str) -> None:
        if not self._execution_guard:
            self._cancel_request()
        self._model.clear()
        self._set_awaiting_commit(False)
        self._applied = None

    @Slot()
    def clearPlan(self) -> None:
        if self._awaiting_commit:
            self.errorOccurred.emit("已应用的计划组尚未提交，不能清空计划")
            return
        self._model.clear()

    @Slot()
    def applyNextGroup(self) -> None:
        if self._busy:
            self.errorOccurred.emit("已有 AI 规划操作正在进行")
            return
        if self._awaiting_commit:
            self.errorOccurred.emit("请先提交已应用的计划组")
            return
        snapshot = self._model.snapshot()
        plan = self._model.current_plan()
        if snapshot is None or plan is None:
            self.errorOccurred.emit("请先生成提交计划")
            return
        settings = self._runtime.planning_settings()
        validation = self._model.validation_result()
        stale = self._model.stale
        serial, cancel_event = self._start_request(clear_prepared=False)
        self._execution_guard = True
        repo = self._git.repo_path or ""

        def work() -> None:
            try:
                if plan.level == "hunk":
                    applied = self._hunk_executor.apply_next(
                        repo,
                        snapshot,
                        plan,
                        validation,
                        stale,
                        settings.limits,
                        settings.timeout_seconds,
                    )
                else:
                    applied = self._executor.apply_next(
                        repo,
                        snapshot,
                        plan,
                        validation,
                        stale,
                        settings.limits,
                    )
                if self._is_current(serial, repo, cancel_event):
                    self._applyFinished.emit(serial, applied)
            except PlanExecutionError as exc:
                logger.warning(f"应用文件级计划失败: {type(exc).__name__}")
                self._execution_guard = False
                self._emit_error_if_current(serial, str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"应用文件级计划异常: {type(exc).__name__}")
                self._execution_guard = False
                self._emit_error_if_current(serial, "应用下一提交组失败")
            finally:
                self._set_busy_if_current(serial, False)

        threading.Thread(target=work, daemon=True).start()

    @Slot()
    def notifyCommitSucceeded(self) -> None:
        applied = self._applied
        if applied is None or not self._awaiting_commit:
            return
        if self._busy:
            return
        serial, cancel_event = self._start_request(clear_prepared=False)
        self._execution_guard = True

        def work() -> None:
            try:
                ok, message = self._executor.verify_committed_group(applied)
                fresh_snapshot = None
                if ok:
                    fresh_snapshot = ChangeContextCollector(
                        self._git, applied.limits
                    ).collect(applied.repo_path, include_unstaged=True)
                if self._is_current(serial, applied.repo_path, cancel_event):
                    self._commitChecked.emit(serial, ok, message, fresh_snapshot)
                else:
                    self._execution_guard = False
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"推进提交计划失败: {type(exc).__name__}")
                self._execution_guard = False
                if self._is_current(serial, applied.repo_path, cancel_event):
                    self._commitChecked.emit(
                        serial,
                        False,
                        "提交成功，但无法建立剩余改动快照，请重新规划",
                        None,
                    )
            finally:
                self._set_busy_if_current(serial, False)

        threading.Thread(target=work, daemon=True).start()

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
        level_name = "代码块级" if plan.level == "hunk" else "文件级"
        self.planReady.emit(True, plan.summary or f"{level_name}提交计划已生成")

    @Slot(int, object)
    def _apply_finished(self, serial: int, applied: AppliedFileGroup) -> None:
        with self._state_lock:
            current = serial == self._serial and not self._cancel_event.is_set()
        if not current:
            return
        self._execution_guard = False
        self._applied = applied
        self._set_awaiting_commit(True)
        group = applied.group
        self.groupApplied.emit(
            group.group_id,
            group.title,
            group.body,
            "下一提交组已暂存，请复核后提交",
        )

    @Slot(int, bool, str, object)
    def _commit_checked(
        self,
        serial: int,
        ok: bool,
        message: str,
        fresh_snapshot: ChangeSnapshot | None,
    ) -> None:
        with self._state_lock:
            current = serial == self._serial and not self._cancel_event.is_set()
        if not current:
            return
        self._execution_guard = False
        applied = self._applied
        self._applied = None
        self._set_awaiting_commit(False)
        if not ok or applied is None or fresh_snapshot is None:
            self._model.markStale()
            self.errorOccurred.emit(message or "后续计划已失效，请重新规划")
            return
        advanced, completed, advance_message = self._model.advance_after_commit(
            applied.group.group_id, fresh_snapshot
        )
        if not advanced:
            self._model.markStale()
            self.errorOccurred.emit(advance_message)
            return
        self.planAdvanced.emit(completed, advance_message)

    @Slot(str, str, str)
    def _workspace_checked(
        self, repo: str, expected_fingerprint: str, current_fingerprint: str
    ) -> None:
        snapshot = self._model.snapshot()
        if (
            snapshot is None
            or repo != (self._git.repo_path or "")
            or snapshot.workspace_fingerprint != expected_fingerprint
        ):
            return
        if not current_fingerprint or current_fingerprint != expected_fingerprint:
            self._model.markStale()

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

    def _set_awaiting_commit(self, value: bool) -> None:
        if self._awaiting_commit == value:
            return
        self._awaiting_commit = value
        self.awaitingCommitChanged.emit()

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
