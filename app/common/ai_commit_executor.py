# coding: utf-8
"""文件级计划的可恢复索引执行器；不提交，也不推送。"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass

from .ai_commit_context import ChangeContextCollector, SnapshotLimits
from .ai_commit_models import (
    ChangeSnapshot,
    CommitGroup,
    CommitPlan,
    PlanValidationResult,
)
from .ai_commit_patch import (
    HunkPatchBuilder,
    IndexPatchApplier,
    PatchValidationError,
    TemporaryIndexValidator,
)
from .git_service import GitService


class PlanExecutionError(RuntimeError):
    """计划不可安全应用，或索引恢复失败。"""


@dataclass(frozen=True)
class AppliedFileGroup:
    repo_path: str
    group: CommitGroup
    head_before: str
    index_tree_before: str
    expected_commit_tree: str
    limits: SnapshotLimits


class FilePlanExecutor:
    """一次只把首组写入索引，失败时用原索引树恢复。"""

    def __init__(self, git_service: GitService):
        self._git = git_service
        self._lock = threading.Lock()

    def apply_next(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        plan: CommitPlan,
        validation: PlanValidationResult,
        stale: bool,
        limits: SnapshotLimits,
    ) -> AppliedFileGroup:
        with self._lock:
            if stale:
                raise PlanExecutionError("计划已过期，请重新规划")
            if not validation.valid or not validation.executable:
                raise PlanExecutionError("计划未通过文件级执行校验")
            if not plan.groups:
                raise PlanExecutionError("计划中没有可应用的提交组")
            if repo_path != (self._git.repo_path or ""):
                raise PlanExecutionError("当前仓库与计划不一致")

            collector = ChangeContextCollector(self._git, limits)
            current_fingerprint = collector.workspace_fingerprint(repo_path)
            if current_fingerprint != snapshot.workspace_fingerprint:
                raise PlanExecutionError("工作区已变化，请重新规划")

            snapshot_paths = {change.path for change in snapshot.changes}
            current_paths = {change.path for change in self._git.get_status_at(repo_path)}
            if not snapshot.include_unstaged and current_paths - snapshot_paths:
                raise PlanExecutionError(
                    "暂存区外还有未纳入计划的改动，请改用全部工作区规划"
                )

            group = plan.groups[0]
            by_id = snapshot.change_by_id("file")
            planned_changes = list(snapshot.changes)
            target_changes = [by_id[item] for item in group.change_ids]
            planned_paths = self._git_paths(planned_changes)
            target_paths = self._git_paths(target_changes)
            if not target_paths:
                raise PlanExecutionError("下一提交组没有可暂存路径")

            index_tree_before = self._write_tree(repo_path)
            try:
                self._reset_paths(repo_path, snapshot.head, planned_paths)
                self._run_required(
                    repo_path,
                    ["--literal-pathspecs", "add", "-A", "--", *target_paths],
                    "暂存下一提交组失败",
                )
                if repo_path != (self._git.repo_path or ""):
                    raise PlanExecutionError("应用期间已切换仓库，已恢复原暂存区")
                if self._git.get_head_at(repo_path) != snapshot.head:
                    raise PlanExecutionError("应用期间 HEAD 已变化，已恢复原暂存区")
                staged_paths = {
                    change.path
                    for change in self._git.get_status_at(repo_path)
                    if change.staged
                }
                expected_paths = {change.path for change in target_changes}
                if staged_paths != expected_paths:
                    raise PlanExecutionError("暂存结果与目标组不一致，已恢复原暂存区")
                expected_tree = self._write_tree(repo_path)
            except Exception as exc:
                restored = self._restore_tree(repo_path, index_tree_before)
                self._git.statusChanged.emit()
                if not restored:
                    raise PlanExecutionError(
                        "应用失败且无法自动恢复暂存区，请立即检查 git status"
                    ) from exc
                if isinstance(exc, PlanExecutionError):
                    raise
                raise PlanExecutionError(str(exc)) from exc

            self._git.statusChanged.emit()
            return AppliedFileGroup(
                repo_path,
                group,
                snapshot.head,
                index_tree_before,
                expected_tree,
                limits,
            )

    def verify_committed_group(
        self, applied: AppliedFileGroup
    ) -> tuple[bool, str]:
        with self._lock:
            if applied.repo_path != (self._git.repo_path or ""):
                return False, "当前仓库与已应用计划不一致"
            current_head = self._git.get_head_at(applied.repo_path)
            if not current_head or current_head == applied.head_before:
                return False, "未检测到对应的新提交"
            ok, output, error = self._git._run_git_sync_at(  # noqa: SLF001
                applied.repo_path, ["rev-list", "--parents", "-n", "1", current_head]
            )
            if not ok:
                return False, self._error_text(error, "无法验证新提交父节点")
            parts = output.strip().split()
            parents = parts[1:]
            expected_parents = [applied.head_before] if applied.head_before else []
            if parents != expected_parents:
                return False, "提交历史与应用计划时不一致，请重新规划"
            ok, tree, error = self._git._run_git_sync_at(  # noqa: SLF001
                applied.repo_path, ["rev-parse", f"{current_head}^{{tree}}"]
            )
            if not ok:
                return False, self._error_text(error, "无法验证新提交树")
            if tree.strip() != applied.expected_commit_tree:
                return False, "实际提交内容超出已应用组，后续计划已失效"
            return True, current_head

    def _reset_paths(self, repo_path: str, head: str, paths: list[str]) -> None:
        if head:
            self._run_required(
                repo_path,
                ["--literal-pathspecs", "reset", "-q", head, "--", *paths],
                "重置计划路径失败",
            )
        else:
            self._run_required(
                repo_path,
                [
                    "--literal-pathspecs", "rm", "--cached", "-r",
                    "--ignore-unmatch", "--", *paths,
                ],
                "准备首次提交索引失败",
            )

    def _write_tree(self, repo_path: str) -> str:
        ok, tree, error = self._git._run_git_sync_at(  # noqa: SLF001
            repo_path, ["write-tree"]
        )
        if not ok or not tree.strip():
            raise PlanExecutionError(self._error_text(error, "无法快照当前暂存区"))
        return tree.strip()

    def _restore_tree(self, repo_path: str, tree: str) -> bool:
        ok, _, _ = self._git._run_git_sync_at(  # noqa: SLF001
            repo_path, ["read-tree", tree]
        )
        if not ok:
            return False
        try:
            return self._write_tree(repo_path) == tree
        except PlanExecutionError:
            return False

    def _run_required(
        self, repo_path: str, args: list[str], fallback: str
    ) -> None:
        ok, output, error = self._git._run_git_sync_at(repo_path, args)  # noqa: SLF001
        if not ok:
            raise PlanExecutionError(self._error_text(error or output, fallback))

    @staticmethod
    def _git_paths(changes: list) -> list[str]:
        paths: list[str] = []
        for change in changes:
            for path in (change.path, change.old_path, change.new_path):
                if path and path not in paths:
                    paths.append(path)
        return paths

    @staticmethod
    def _error_text(value: str, fallback: str) -> str:
        text = value.strip()
        return text[-1000:] if text else fallback


class HunkPlanExecutor(FilePlanExecutor):
    """整份计划先隔离验证，再只把首个代码块组写入真实索引。"""

    def apply_next(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        plan: CommitPlan,
        validation: PlanValidationResult,
        stale: bool,
        limits: SnapshotLimits,
        timeout_seconds: int,
    ) -> AppliedFileGroup:
        with self._lock:
            self._validate_preconditions(
                repo_path, snapshot, plan, validation, stale, limits
            )
            expected_tree = self._temporary_first_tree(
                repo_path, snapshot, plan, validation, limits, timeout_seconds
            )
            return self._apply_first_group(
                repo_path, snapshot, plan, expected_tree, limits, timeout_seconds
            )

    def _validate_preconditions(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        plan: CommitPlan,
        validation: PlanValidationResult,
        stale: bool,
        limits: SnapshotLimits,
    ) -> None:
        if stale:
            raise PlanExecutionError("计划已过期，请重新规划")
        if plan.level != "hunk" or not plan.groups:
            raise PlanExecutionError("代码块执行器只接受非空代码块级计划")
        if not validation.valid or not validation.executable:
            raise PlanExecutionError("计划未通过代码块级执行校验")
        if repo_path != (self._git.repo_path or ""):
            raise PlanExecutionError("当前仓库与计划不一致")
        collector = ChangeContextCollector(self._git, limits)
        if collector.workspace_fingerprint(repo_path) != snapshot.workspace_fingerprint:
            raise PlanExecutionError("工作区已变化，请重新规划")
        snapshot_paths = {change.path for change in snapshot.changes}
        current_paths = {change.path for change in self._git.get_status_at(repo_path)}
        if not snapshot.include_unstaged and current_paths - snapshot_paths:
            raise PlanExecutionError(
                "暂存区外还有未纳入计划的改动，请改用全部工作区规划"
            )

    def _temporary_first_tree(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        plan: CommitPlan,
        validation: PlanValidationResult,
        limits: SnapshotLimits,
        timeout_seconds: int,
    ) -> str:
        try:
            temporary = TemporaryIndexValidator(self._git).validate(
                repo_path, snapshot, plan, validation, limits, timeout_seconds
            )
        except PatchValidationError as exc:
            raise PlanExecutionError(str(exc)) from exc
        expected_tree = dict(temporary.group_trees).get(
            plan.groups[0].group_id, ""
        )
        if not expected_tree:
            raise PlanExecutionError("隔离索引未生成首组目标树")
        return expected_tree

    def _apply_first_group(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        plan: CommitPlan,
        expected_tree: str,
        limits: SnapshotLimits,
        timeout_seconds: int,
    ) -> AppliedFileGroup:
        group = plan.groups[0]
        index_tree_before = self._write_tree(repo_path)
        try:
            self._write_real_group(
                repo_path, snapshot, group, expected_tree, timeout_seconds
            )
        except Exception as exc:
            self._restore_after_failure(repo_path, index_tree_before, exc)
        self._git.statusChanged.emit()
        return AppliedFileGroup(
            repo_path, group, snapshot.head, index_tree_before,
            expected_tree, limits,
        )

    def _write_real_group(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        group: CommitGroup,
        expected_tree: str,
        timeout_seconds: int,
    ) -> None:
        self._reset_paths(
            repo_path, snapshot.head, self._git_paths(list(snapshot.changes))
        )
        built = HunkPatchBuilder.build_group(snapshot, group)
        IndexPatchApplier.apply_group(
            repo_path,
            built,
            snapshot.change_by_id("hunk"),
            os.environ.copy(),
            timeout_seconds,
        )
        if repo_path != (self._git.repo_path or ""):
            raise PlanExecutionError("应用期间已切换仓库，已恢复原暂存区")
        if self._git.get_head_at(repo_path) != snapshot.head:
            raise PlanExecutionError("应用期间 HEAD 已变化，已恢复原暂存区")
        if self._write_tree(repo_path) != expected_tree:
            raise PlanExecutionError("真实索引与隔离验证结果不一致，已恢复原暂存区")

    def _restore_after_failure(
        self, repo_path: str, index_tree_before: str, error: Exception
    ) -> None:
        restored = self._restore_tree(repo_path, index_tree_before)
        self._git.statusChanged.emit()
        if not restored:
            raise PlanExecutionError(
                "应用失败且无法自动恢复暂存区，请立即检查 git status"
            ) from error
        if isinstance(error, PlanExecutionError):
            raise error
        raise PlanExecutionError(str(error)) from error
