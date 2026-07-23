# coding: utf-8
"""文件级与代码块级 AI 提交规划异步桥。"""
from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.common.ai_commit_context import ChangeContextCollector, SnapshotCollectionError
from app.common.ai_commit_executor import (
    AppliedFileGroup,
    FilePlanExecutor,
    HunkPlanExecutor,
    PlanExecutionError,
)
from app.common.ai_commit_http import endpoint_requires_remote_consent
from app.common.ai_commit_models import (
    ChangeSnapshot, CommitPlan, CommitPlanValidator, PlanProtocolError,
    PlannerRequest,
)
from app.common.ai_commit_provider import ProviderCancelledError
from app.common.ai_commit_schema import build_user_input, normalize_output_language
from app.common.ai_commit_settings import AiCommitSettings, AiCommitSettingsError
from app.common.git_service import GitService
from app.common.logger import get_logger
from app_qml.backend.ai_commit_plan_model import AiCommitPlanModel
from app_qml.backend.ai_commit_auto_flow import AiCommitAutoFlowMixin
from app_qml.backend.ai_commit_plan_request_state import (
    PlannerRuntime,
    PlanRequestState,
    PreparedPlanRequest,
    ensure_plan_fingerprint,
)


logger = get_logger("AiCommitPlanBridge")


class AiCommitPlanBridge(AiCommitAutoFlowMixin, QObject):
    """协调快照、分组提交和最终推送。"""

    busyChanged = Signal()
    awaitingCommitChanged = Signal()
    contextPrepared = Signal(str, bool, int, int, str)
    planReady = Signal(bool, str)
    groupApplied = Signal(str, str, str, str)
    planAdvanced = Signal(bool, str)
    planCommitPushFinished = Signal(bool, str)
    errorOccurred = Signal(str)
    _resolved = Signal(int, str, object, object)
    _applyFinished = Signal(int, object)
    _commitChecked = Signal(int, bool, str, object)
    _autoPushFinished = Signal(int, bool, str)
    _workspaceChecked = Signal(str, str, str)

    def __init__(
        self,
        git_service: GitService,
        runtime: PlannerRuntime,
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
        self._awaiting_commit = False
        self._execution_guard = False
        self._applied: AppliedFileGroup | None = None
        self._auto_commit_push = False
        self._auto_completed_groups = 0
        self._auto_repo_path = ""
        self._request_state = PlanRequestState(
            lambda: self._git.repo_path or "",
            self.busyChanged.emit,
        )
        self._resolved.connect(self._apply_resolved)
        self._applyFinished.connect(self._apply_finished)
        self._commitChecked.connect(self._commit_checked)
        self._autoPushFinished.connect(self._auto_push_finished)
        self._workspaceChecked.connect(self._workspace_checked)

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._request_state.busy

    @Property(bool, notify=awaitingCommitChanged)
    def awaitingCommit(self) -> bool:
        return self._awaiting_commit

    @Property(QObject, constant=True)
    def planModel(self) -> QObject:
        return self._model

    @Slot()
    def preparePlan(self) -> None:
        self._prepare_plan("file", "")

    @Slot(str)
    def preparePlanForLanguage(self, output_language: str) -> None:
        """按当前 UI 语言准备文件级规划。"""
        self._prepare_plan("file", output_language)

    @Slot()
    def prepareHunkPlan(self) -> None:
        self._prepare_plan("hunk", "")

    @Slot(str)
    def prepareHunkPlanForLanguage(self, output_language: str) -> None:
        """按当前 UI 语言准备代码块级规划。"""
        self._prepare_plan("hunk", output_language)

    def _prepare_plan(self, level: str, output_language: str) -> None:
        if self._execution_guard:
            self.errorOccurred.emit("上一暂存执行仍在收尾，请稍候")
            return
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
        # AI 提交入口固定分析整个工作区，避免旧版 staged 配置漏掉未暂存/未跟踪改动。
        include_unstaged = True

        def work() -> None:
            try:
                snapshot = ChangeContextCollector(
                    self._git, settings.limits
                ).collect(repo, include_unstaged=include_unstaged)
                if not snapshot.changes:
                    scope = "工作区" if include_unstaged else "暂存区"
                    raise SnapshotCollectionError(f"{scope}没有可规划的改动")
                request = PlannerRequest(
                    snapshot,
                    "plan",
                    level,
                    settings.generate_body,
                    normalize_output_language(output_language),
                )
                request_id = f"plan-{level}-{serial}-{snapshot.snapshot_id[:16]}"
                prepared = PreparedPlanRequest(
                    request_id,
                    repo,
                    snapshot,
                    request,
                    settings,
                    settings.provider != "ollama"
                    or endpoint_requires_remote_consent(settings.local_endpoint),
                )
                if not self._request_state.store_prepared_if_current(
                    serial, repo, cancel_event, prepared
                ):
                    return
                scope_summary = "分析已暂存、未暂存和未跟踪改动"
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
        prepared = self._request_state.take_prepared(request_id)
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
                ensure_plan_fingerprint(collector, prepared)
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
                ensure_plan_fingerprint(collector, prepared)
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
        self._request_state.cancel_prepared(request_id)

    @Slot()
    def cancelCurrent(self) -> None:
        if self._execution_guard:
            self.errorOccurred.emit("暂存执行不能中途取消，请等待完成")
            return
        self._cancel_request()

    @Slot()
    def invalidateSettings(self) -> None:
        """配置或凭据变化时取消尚未执行的模型请求，保留已校验计划。"""
        if not self._execution_guard:
            self._cancel_request()

    @Slot()
    def invalidateWorkspace(self) -> None:
        if self._execution_guard or self._awaiting_commit:
            return
        if self.busy:
            self._cancel_request()
            self._model.markStale()
            return
        snapshot = self._model.snapshot()
        if snapshot is None:
            if self._request_state.has_prepared:
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
        applied_to_restore = (
            self._applied
            if self._awaiting_commit and not self._execution_guard
            else None
        )
        if self._auto_commit_push:
            self._cancel_request()
            self._auto_commit_push = False
            self._auto_repo_path = ""
            self._execution_guard = False
        elif not self._execution_guard:
            self._cancel_request()
        self._model.clear()
        self._set_awaiting_commit(False)
        self._applied = None
        if applied_to_restore is not None:
            self._execution_guard = True
            threading.Thread(
                target=self._restore_discarded_apply,
                args=(applied_to_restore,),
                daemon=True,
            ).start()

    @Slot()
    def clearPlan(self) -> None:
        if self._awaiting_commit or self._auto_commit_push:
            self.errorOccurred.emit("已应用的计划组尚未提交，不能清空计划")
            return
        self._model.clear()

    @Slot()
    def commitPlanAndPush(self) -> None:
        """按计划逐组提交，全部成功后只推送一次。"""
        if self._execution_guard or self.busy or self._awaiting_commit:
            self.errorOccurred.emit("已有 AI 提交操作正在进行")
            return
        if self._model.snapshot() is None or self._model.current_plan() is None:
            self.errorOccurred.emit("请先生成提交计划")
            return
        if not self._model.executable:
            self.errorOccurred.emit("提交计划未通过执行校验")
            return
        self._auto_commit_push = True
        self._auto_completed_groups = 0
        self._auto_repo_path = self._git.repo_path or ""
        self.applyNextGroup()

    @Slot()
    def applyNextGroup(self) -> None:
        if self._execution_guard:
            self.errorOccurred.emit("上一暂存执行仍在收尾，请稍候")
            return
        if self.busy:
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
                else:
                    self._restore_discarded_apply(applied)
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
        if self.busy:
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
        if (
            not self._request_state.is_serial_current(serial)
            or repo != (self._git.repo_path or "")
        ):
            return
        self._model.load(plan, snapshot)
        level_name = "代码块级" if plan.level == "hunk" else "文件级"
        self.planReady.emit(True, plan.summary or f"{level_name}提交计划已生成")

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

    def _start_request(self, clear_prepared: bool) -> tuple[int, threading.Event]:
        return self._request_state.start(clear_prepared)

    def _cancel_request(self) -> None:
        self._request_state.cancel()

    def _set_awaiting_commit(self, value: bool) -> None:
        if self._awaiting_commit == value:
            return
        self._awaiting_commit = value
        self.awaitingCommitChanged.emit()

    def _set_busy_if_current(self, serial: int, value: bool) -> None:
        self._request_state.set_busy_if_current(serial, value)

    def _is_current(
        self, serial: int, repo: str, event: threading.Event
    ) -> bool:
        return self._request_state.is_current(serial, repo, event)

    def _restore_discarded_apply(self, applied: AppliedFileGroup) -> None:
        try:
            ok, message = self._executor.restore_uncommitted_group(applied)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"恢复被丢弃的 AI 暂存结果异常: {type(exc).__name__}")
            ok = False
            message = "恢复暂存区时发生异常，请立即检查 git status"
        if ok:
            logger.warning("已恢复切仓库前的 AI 计划暂存区")
        else:
            logger.error("无法安全恢复被丢弃的 AI 计划暂存结果")
        try:
            self.errorOccurred.emit(message)
        finally:
            self._execution_guard = False

    def _emit_error_if_current(self, serial: int, message: str) -> None:
        if self._request_state.is_serial_current(serial):
            if self._auto_commit_push:
                self._finish_auto_commit_failure(message)
            else:
                self.errorOccurred.emit(message)
