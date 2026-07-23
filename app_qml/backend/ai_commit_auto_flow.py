# coding: utf-8
"""AI 分组提交并最终推送的自动流程混入。"""
from __future__ import annotations

import threading

from PySide6.QtCore import Slot

from app.common.ai_commit_context import ChangeContextCollector
from app.common.ai_commit_executor import AppliedFileGroup
from app.common.ai_commit_models import ChangeSnapshot
from app.common.logger import get_logger


logger = get_logger("AiCommitAutoFlow")


class AiCommitAutoFlowMixin:
    """在计划桥已有的逐组执行状态机上自动提交并推送。"""

    def _apply_finished(self, serial: int, applied: AppliedFileGroup) -> None:
        if (
            not self._request_state.is_serial_current(serial)
            or applied.repo_path != (self._git.repo_path or "")
        ):
            threading.Thread(
                target=self._restore_discarded_apply,
                args=(applied,),
                daemon=True,
            ).start()
            return
        self._execution_guard = False
        self._applied = applied
        if self._auto_commit_push:
            self._start_auto_commit()
            return
        self._set_awaiting_commit(True)
        group = applied.group
        self.groupApplied.emit(
            group.group_id,
            group.title,
            group.body,
            "下一提交组已暂存，请复核后提交",
        )

    def _commit_checked(
        self,
        serial: int,
        ok: bool,
        message: str,
        fresh_snapshot: ChangeSnapshot | None,
    ) -> None:
        if not self._request_state.is_serial_current(serial):
            return
        # 提交校验信号可能先于 worker 的 finally 到达；先释放本次请求的
        # busy 状态，再启动下一组，否则第二组会被竞态误判为“仍在进行”。
        self._set_busy_if_current(serial, False)
        self._execution_guard = False
        applied = self._applied
        self._applied = None
        self._set_awaiting_commit(False)
        if not ok or applied is None or fresh_snapshot is None:
            self._model.markStale()
            failure = message or "后续计划已失效，请重新规划"
            if self._auto_commit_push:
                self._finish_auto_commit_failure(failure)
            else:
                self.errorOccurred.emit(failure)
            return
        advanced, completed, advance_message = self._model.advance_after_commit(
            applied.group.group_id, fresh_snapshot
        )
        if not advanced:
            self._model.markStale()
            if self._auto_commit_push:
                self._finish_auto_commit_failure(advance_message)
            else:
                self.errorOccurred.emit(advance_message)
            return
        if self._auto_commit_push:
            self._auto_completed_groups += 1
            if completed:
                self._start_auto_push()
            else:
                self.applyNextGroup()
            return
        self.planAdvanced.emit(completed, advance_message)

    def _start_auto_commit(self) -> None:
        applied = self._applied
        snapshot = self._model.snapshot()
        plan = self._model.current_plan()
        if applied is None or snapshot is None or plan is None:
            self._finish_auto_commit_failure("提交计划上下文已失效，请重新规划")
            return
        plan_level = plan.level
        settings = self._runtime.planning_settings()
        serial, cancel_event = self._start_request(clear_prepared=False)
        self._execution_guard = True

        def work() -> None:
            try:
                body = applied.group.body.strip()
                message = applied.group.title.strip()
                if body:
                    message += "\n\n" + body
                ok, commit_message = self._git.commit_at(applied.repo_path, message)
                fresh_snapshot = None
                if not ok:
                    executor = (
                        self._hunk_executor
                        if plan_level == "hunk" else self._executor
                    )
                    restored, restore_message = executor.restore_uncommitted_group(
                        applied
                    )
                    if not restored:
                        commit_message = f"{commit_message}；{restore_message}"
                else:
                    fresh_snapshot = ChangeContextCollector(
                        self._git, settings.limits
                    ).collect(
                        applied.repo_path,
                        include_unstaged=snapshot.include_unstaged,
                    )
                if self._is_current(serial, applied.repo_path, cancel_event):
                    self._commitChecked.emit(
                        serial, ok, commit_message, fresh_snapshot
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"自动提交计划组异常: {type(exc).__name__}")
                self._execution_guard = False
                self._emit_error_if_current(serial, "自动提交计划组失败")
            finally:
                self._set_busy_if_current(serial, False)

        threading.Thread(target=work, daemon=True).start()

    def _start_auto_push(self) -> None:
        if self._git.repo_path != self._auto_repo_path:
            self._finish_auto_commit_failure("当前仓库已切换，未执行最终推送")
            return
        serial, _cancel_event = self._start_request(clear_prepared=False)
        self._execution_guard = True
        branch = self._git.get_current_branch()
        self._git.push(
            "origin",
            branch,
            callback=lambda ok, message: self._autoPushFinished.emit(
                serial, ok, message
            ),
        )

    @Slot(int, bool, str)
    def _auto_push_finished(self, serial: int, ok: bool, message: str) -> None:
        if not self._request_state.is_serial_current(serial):
            return
        self._execution_guard = False
        self._auto_commit_push = False
        self._auto_repo_path = ""
        self._set_busy_if_current(serial, False)
        if ok:
            result = f"已完成 {self._auto_completed_groups} 个 Commit，并推送成功"
        else:
            result = (
                f"已完成 {self._auto_completed_groups} 个 Commit，但推送失败："
                f"{message or '未知错误'}"
            )
        self.planCommitPushFinished.emit(ok, result)

    def _finish_auto_commit_failure(self, message: str) -> None:
        self._execution_guard = False
        self._auto_commit_push = False
        self._auto_repo_path = ""
        result = (
            f"已完成 {self._auto_completed_groups} 个 Commit，后续操作失败："
            f"{message or '未知错误'}"
        )
        self.planCommitPushFinished.emit(False, result)
