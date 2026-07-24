# coding: utf-8
"""文件级与代码块级 AI 提交规划异步桥。"""
from __future__ import annotations

import threading
from dataclasses import replace
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
from app.common.ai_commit_schema import (
    build_user_input,
    granularity_issues,
    normalize_output_language,
)
from app.common.ai_commit_settings import AiCommitSettings, AiCommitSettingsError
from app.common.git_service import GitService
from app.common.logger import get_logger
from app.common.prism_task import submit_to_pool
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

        def work() -> tuple[PreparedPlanRequest, int, int]:
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
            return (
                prepared,
                len(snapshot.expected_ids(level)),
                len(build_user_input(request)),
            )

        def succeeded(result: object) -> None:
            prepared, change_count, character_count = result
            if self._request_state.store_prepared_if_current(
                serial, repo, cancel_event, prepared
            ):
                self.contextPrepared.emit(
                    prepared.request_id,
                    prepared.is_remote,
                    change_count,
                    character_count,
                    "分析已暂存、未暂存和未跟踪改动",
                )
            self._set_busy_if_current(serial, False)

        def failed(exc: BaseException) -> None:
            if isinstance(exc, (SnapshotCollectionError, AiCommitSettingsError)):
                logger.warning(f"准备 {level} 规划失败: {type(exc).__name__}")
                self._emit_error_if_current(serial, str(exc))
            else:
                logger.error(
                    f"准备 {level} 规划异常: {type(exc).__name__}: {exc}"
                )
                self._emit_error_if_current(serial, "准备提交规划上下文失败")
            self._set_busy_if_current(serial, False)

        submit_to_pool(work, on_success=succeeded, on_failure=failed)

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

        def work() -> CommitPlan:
            collector = ChangeContextCollector(self._git, prepared.settings.limits)
            ensure_plan_fingerprint(collector, prepared)
            provider = self._runtime.create_provider_for(prepared.settings)
            raw_plan = provider.generate_plan(prepared.request, cancel_event)
            plan = CommitPlan.from_mapping(raw_plan)
            issues = granularity_issues(
                prepared.request,
                [len(group.change_ids) for group in plan.groups],
            )
            if issues:
                logger.warning(
                    "模型计划违反固定拆分粒度，发起重试: %s",
                    "；".join(issues),
                )
                ensure_plan_fingerprint(collector, prepared)
                retry_request = replace(prepared.request, mode="plan_retry")
                raw_plan = provider.generate_plan(retry_request, cancel_event)
                plan = CommitPlan.from_mapping(raw_plan)
                issues = granularity_issues(
                    prepared.request,
                    [len(group.change_ids) for group in plan.groups],
                )
            if issues:
                raise PlanProtocolError(
                    f"模型未按固定拆分粒度规划，请重新生成：{'；'.join(issues)}"
                )
            result = self._validator.validate(
                plan,
                prepared.snapshot,
                expected_level=prepared.request.level,
            )
            if not result.valid:
                details = "；".join(issue.message for issue in result.issues)
                raise PlanProtocolError(details or "模型计划校验失败")
            ensure_plan_fingerprint(collector, prepared)
            return plan

        def succeeded(plan: object) -> None:
            if self._is_current(serial, prepared.repo_path, cancel_event):
                self._apply_resolved(
                    serial, prepared.repo_path, plan, prepared.snapshot
                )
            self._set_busy_if_current(serial, False)

        def failed(exc: BaseException) -> None:
            if isinstance(exc, ProviderCancelledError):
                self._set_busy_if_current(serial, False)
                return
            if isinstance(exc, (
                AiCommitSettingsError,
                PlanProtocolError,
                SnapshotCollectionError,
                RuntimeError,
                ValueError,
            )):
                logger.warning(f"生成文件级规划失败: {type(exc).__name__}")
                self._emit_error_if_current(serial, str(exc))
            else:
                logger.error(
                    f"生成文件级规划异常: {type(exc).__name__}: {exc}"
                )
                self._emit_error_if_current(serial, "生成文件级规划失败")
            self._set_busy_if_current(serial, False)

        submit_to_pool(work, on_success=succeeded, on_failure=failed)

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

        submit_to_pool(
            lambda: ChangeContextCollector(
                self._git, settings.limits
            ).workspace_fingerprint(repo),
            on_success=lambda current: self._workspace_checked(
                repo, expected, str(current)
            ),
            on_failure=lambda exc: self._workspace_check_failed(
                repo, expected, exc
            ),
        )

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
            self._submit_restore_discarded_apply(applied_to_restore)

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

        def work() -> AppliedFileGroup:
            if plan.level == "hunk":
                return self._hunk_executor.apply_next(
                    repo,
                    snapshot,
                    plan,
                    validation,
                    stale,
                    settings.limits,
                    settings.timeout_seconds,
                )
            return self._executor.apply_next(
                repo,
                snapshot,
                plan,
                validation,
                stale,
                settings.limits,
            )

        def succeeded(applied: object) -> None:
            self._set_busy_if_current(serial, False)
            if self._is_current(serial, repo, cancel_event):
                self._apply_finished(serial, applied)
            else:
                self._submit_restore_discarded_apply(applied)

        def failed(exc: BaseException) -> None:
            self._execution_guard = False
            if isinstance(exc, PlanExecutionError):
                logger.warning(f"应用文件级计划失败: {type(exc).__name__}")
                self._emit_error_if_current(serial, str(exc))
            else:
                logger.error(
                    f"应用文件级计划异常: {type(exc).__name__}: {exc}"
                )
                self._emit_error_if_current(serial, "应用下一提交组失败")
            self._set_busy_if_current(serial, False)

        submit_to_pool(work, on_success=succeeded, on_failure=failed)

    @Slot()
    def notifyCommitSucceeded(self) -> None:
        applied = self._applied
        if applied is None or not self._awaiting_commit:
            return
        if self.busy:
            return
        serial, cancel_event = self._start_request(clear_prepared=False)
        self._execution_guard = True

        def work() -> tuple[bool, str, ChangeSnapshot | None]:
            ok, message = self._executor.verify_committed_group(applied)
            fresh_snapshot = None
            if ok:
                fresh_snapshot = ChangeContextCollector(
                    self._git, applied.limits
                ).collect(applied.repo_path, include_unstaged=True)
            return ok, message, fresh_snapshot

        def succeeded(result: object) -> None:
            self._set_busy_if_current(serial, False)
            if self._is_current(serial, applied.repo_path, cancel_event):
                ok, message, fresh_snapshot = result
                self._commit_checked(
                    serial, ok, message, fresh_snapshot
                )
            else:
                self._execution_guard = False

        def failed(exc: BaseException) -> None:
            logger.error(
                f"推进提交计划失败: {type(exc).__name__}: {exc}"
            )
            self._execution_guard = False
            if self._is_current(serial, applied.repo_path, cancel_event):
                self._commit_checked(
                    serial,
                    False,
                    "提交成功，但无法建立剩余改动快照，请重新规划",
                    None,
                )
            self._set_busy_if_current(serial, False)

        submit_to_pool(work, on_success=succeeded, on_failure=failed)

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

    def _workspace_check_failed(
        self, repo: str, expected_fingerprint: str, exc: BaseException
    ) -> None:
        logger.warning(
            f"复验规划工作区失败: {type(exc).__name__}: {exc}"
        )
        self._workspace_checked(repo, expected_fingerprint, "")

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

    def _restore_discarded_apply(
        self, applied: AppliedFileGroup
    ) -> tuple[bool, str]:
        """恢复暂存区；只执行 Git/文件工作，不修改 QObject 状态。"""
        try:
            return self._executor.restore_uncommitted_group(applied)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"恢复被丢弃的 AI 暂存结果异常: {type(exc).__name__}")
            return False, "恢复暂存区时发生异常，请立即检查 git status"

    def _submit_restore_discarded_apply(
        self, applied: AppliedFileGroup
    ) -> None:
        submit_to_pool(
            self._restore_discarded_apply,
            applied,
            on_success=self._restore_discarded_apply_finished,
            on_failure=lambda exc: self._restore_discarded_apply_finished(
                (False, f"恢复暂存区时发生异常: {exc}")
            ),
        )

    def _restore_discarded_apply_finished(self, result: object) -> None:
        ok, message = result
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
