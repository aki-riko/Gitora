# coding: utf-8
"""可由 QML 编辑、每次变更后确定性复验的提交计划模型。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.common.ai_commit_models import (
    ChangeSnapshot,
    CommitGroup,
    CommitPlan,
    CommitPlanValidator,
    FileChangeSnapshot,
    PlanValidationResult,
)


@dataclass
class _EditableGroup:
    group_id: str
    title: str
    body: str
    change_ids: list[str]
    depends_on: list[str]
    rationale: str
    warnings: list[str]


class AiCommitPlanModel(QObject):
    """模型输出只是初稿；所有人工调整都会重新经过同一验证器。"""

    planChanged = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._validator = CommitPlanValidator()
        self._snapshot: ChangeSnapshot | None = None
        self._summary = ""
        self._plan_warnings: list[str] = []
        self._groups: list[_EditableGroup] = []
        self._unassigned: list[str] = []
        self._result = PlanValidationResult(False, False, (), ())
        self._stale = False
        self._manual_serial = 0

    @Property(bool, notify=planChanged)
    def hasPlan(self) -> bool:
        return self._snapshot is not None

    @Property(str, notify=planChanged)
    def snapshotId(self) -> str:
        return self._snapshot.snapshot_id if self._snapshot else ""

    @Property(str, notify=planChanged)
    def summary(self) -> str:
        return self._summary

    @Property(bool, notify=planChanged)
    def valid(self) -> bool:
        return self._result.valid

    @Property(bool, notify=planChanged)
    def executable(self) -> bool:
        return self._result.executable and not self._stale

    @Property(bool, notify=planChanged)
    def stale(self) -> bool:
        return self._stale

    @Property("QVariantList", notify=planChanged)
    def groups(self) -> list[dict]:
        if not self._snapshot:
            return []
        changes = self._snapshot.change_by_id("file")
        return [
            {
                "groupId": group.group_id,
                "title": group.title,
                "body": group.body,
                "dependsOn": list(group.depends_on),
                "rationale": group.rationale,
                "warnings": list(group.warnings),
                "changes": [
                    self._change_payload(change_id, group.group_id, changes)
                    for change_id in group.change_ids
                    if change_id in changes
                ],
            }
            for group in self._groups
        ]

    @Property("QVariantList", notify=planChanged)
    def unassignedChanges(self) -> list[dict]:
        if not self._snapshot:
            return []
        changes = self._snapshot.change_by_id("file")
        return [
            self._change_payload(change_id, "", changes)
            for change_id in self._unassigned
            if change_id in changes
        ]

    @Property("QVariantList", notify=planChanged)
    def issues(self) -> list[dict]:
        result = [
            {
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity,
            }
            for issue in self._result.issues
        ]
        result.extend(
            {"code": "model_warning", "message": item, "severity": "warning"}
            for item in self._plan_warnings
        )
        if self._stale:
            result.append({
                "code": "stale_plan",
                "message": "工作区已变化，计划已过期",
                "severity": "error",
            })
        return result

    def load(self, plan: CommitPlan, snapshot: ChangeSnapshot) -> None:
        self._snapshot = snapshot
        self._summary = plan.summary
        self._plan_warnings = list(plan.warnings)
        self._groups = [
            _EditableGroup(
                group.group_id,
                group.title,
                group.body,
                list(group.change_ids),
                list(group.depends_on),
                group.rationale,
                list(group.warnings),
            )
            for group in plan.groups
        ]
        self._unassigned = list(plan.unassigned_change_ids)
        self._stale = False
        self._manual_serial = 0
        self._revalidate()
        self.planChanged.emit()

    @Slot()
    def clear(self) -> None:
        if self._snapshot is None:
            return
        self._snapshot = None
        self._summary = ""
        self._plan_warnings = []
        self._groups = []
        self._unassigned = []
        self._result = PlanValidationResult(False, False, (), ())
        self._stale = False
        self.planChanged.emit()

    @Slot()
    def markStale(self) -> None:
        if self._snapshot is None or self._stale:
            return
        self._stale = True
        self.planChanged.emit()

    @Slot(str, str, str, result=bool)
    def updateGroupMessage(self, group_id: str, title: str, body: str) -> bool:
        group = self._find_group(group_id)
        if group is None:
            return False
        group.title = title.strip()
        group.body = body.strip()
        self._changed()
        return True

    @Slot(str, str, result=bool)
    def moveChange(self, change_id: str, target_group_id: str) -> bool:
        if not self._snapshot or change_id not in self._snapshot.change_by_id("file"):
            return False
        target = self._find_group(target_group_id) if target_group_id else None
        if target_group_id and target is None:
            return False
        for group in self._groups:
            if change_id in group.change_ids:
                group.change_ids.remove(change_id)
        if change_id in self._unassigned:
            self._unassigned.remove(change_id)
        if target is None:
            self._unassigned.append(change_id)
        else:
            target.change_ids.append(change_id)
        self._changed()
        return True

    @Slot(str, int, result=bool)
    def moveGroup(self, group_id: str, new_index: int) -> bool:
        old_index = next(
            (index for index, group in enumerate(self._groups)
             if group.group_id == group_id),
            -1,
        )
        if old_index < 0 or not 0 <= new_index < len(self._groups):
            return False
        group = self._groups.pop(old_index)
        self._groups.insert(new_index, group)
        self._changed()
        return True

    @Slot(result=str)
    def addGroup(self) -> str:
        existing = {group.group_id for group in self._groups}
        while True:
            self._manual_serial += 1
            group_id = f"manual-{self._manual_serial}"
            if group_id not in existing:
                break
        self._groups.append(_EditableGroup(
            group_id, "", "", [], [], "用户手动新增", []
        ))
        self._changed()
        return group_id

    @Slot(str, result=bool)
    def removeEmptyGroup(self, group_id: str) -> bool:
        group = self._find_group(group_id)
        if group is None or group.change_ids:
            return False
        self._groups.remove(group)
        for other in self._groups:
            other.depends_on = [item for item in other.depends_on if item != group_id]
        self._changed()
        return True

    @Slot(str, result=str)
    def getGroupPatch(self, group_id: str) -> str:
        if not self._snapshot:
            return ""
        group = self._find_group(group_id)
        if group is None:
            return ""
        changes = self._snapshot.change_by_id("file")
        sections = []
        for change_id in group.change_ids:
            change = changes.get(change_id)
            if change is not None:
                sections.append(f"# {change.path}\n{change.patch}".rstrip())
        return "\n\n".join(sections)

    def current_plan(self) -> CommitPlan | None:
        if not self._snapshot:
            return None
        return self._build_plan()

    def snapshot(self) -> ChangeSnapshot | None:
        return self._snapshot

    def validation_result(self) -> PlanValidationResult:
        return self._result

    def advance_after_commit(
        self,
        completed_group_id: str,
        fresh_snapshot: ChangeSnapshot,
    ) -> tuple[bool, bool, str]:
        """把已提交首组从会话移除，并按路径映射剩余 change_id。"""
        if not self._snapshot or not self._groups:
            return False, False, "没有可推进的计划"
        if self._groups[0].group_id != completed_group_id:
            return False, False, "已提交组与计划顺序不一致"
        remaining_groups = self._groups[1:]
        if not remaining_groups:
            if fresh_snapshot.changes:
                return False, False, "最后一组提交后仍有新改动，请重新规划"
            self.clear()
            return True, True, "全部计划组已完成"

        old_changes = self._snapshot.change_by_id("file")
        old_path_to_id: dict[str, str] = {}
        for group in remaining_groups:
            for change_id in group.change_ids:
                change = old_changes.get(change_id)
                if change is None or change.path in old_path_to_id:
                    return False, False, "剩余计划路径无法唯一映射"
                old_path_to_id[change.path] = change_id

        fresh_by_path: dict[str, FileChangeSnapshot] = {}
        for change in fresh_snapshot.changes:
            if change.path in fresh_by_path:
                return False, False, "提交后出现部分暂存文件，请重新规划"
            fresh_by_path[change.path] = change
        if set(fresh_by_path) != set(old_path_to_id):
            return False, False, "提交后工作区改动与剩余计划不一致"

        new_id_by_old = {
            old_id: fresh_by_path[path].change_id
            for path, old_id in old_path_to_id.items()
        }
        for path, old_id in old_path_to_id.items():
            if not self._same_change_content(
                old_changes[old_id], fresh_by_path[path]
            ):
                return False, False, f"{path} 在提交期间发生变化，请重新规划"
        completed = completed_group_id
        plan = CommitPlan(
            schema_version="1",
            snapshot_id=fresh_snapshot.snapshot_id,
            level="file",
            summary=self._summary,
            groups=tuple(
                CommitGroup(
                    group.group_id,
                    group.title,
                    group.body,
                    tuple(new_id_by_old[item] for item in group.change_ids),
                    tuple(item for item in group.depends_on if item != completed),
                    group.rationale,
                    tuple(group.warnings),
                )
                for group in remaining_groups
            ),
            unassigned_change_ids=(),
            warnings=tuple(self._plan_warnings),
        )
        self.load(plan, fresh_snapshot)
        return True, False, "已推进到下一提交组"

    @staticmethod
    def _same_change_content(
        before: FileChangeSnapshot, after: FileChangeSnapshot
    ) -> bool:
        return (
            before.path,
            before.old_path,
            before.new_path,
            before.status,
            before.binary,
            before.truncated,
            before.unsupported_reason,
            before.additions,
            before.deletions,
            before.patch,
        ) == (
            after.path,
            after.old_path,
            after.new_path,
            after.status,
            after.binary,
            after.truncated,
            after.unsupported_reason,
            after.additions,
            after.deletions,
            after.patch,
        )

    def _changed(self) -> None:
        self._revalidate()
        self.planChanged.emit()

    def _revalidate(self) -> None:
        if not self._snapshot:
            self._result = PlanValidationResult(False, False, (), ())
            return
        self._result = self._validator.validate(
            self._build_plan(), self._snapshot, expected_level="file"
        )

    def _build_plan(self) -> CommitPlan:
        assert self._snapshot is not None
        return CommitPlan(
            schema_version="1",
            snapshot_id=self._snapshot.snapshot_id,
            level="file",
            summary=self._summary,
            groups=tuple(
                CommitGroup(
                    group.group_id,
                    group.title,
                    group.body,
                    tuple(group.change_ids),
                    tuple(group.depends_on),
                    group.rationale,
                    tuple(group.warnings),
                )
                for group in self._groups
            ),
            unassigned_change_ids=tuple(self._unassigned),
            warnings=tuple(self._plan_warnings),
        )

    def _find_group(self, group_id: str) -> _EditableGroup | None:
        return next(
            (group for group in self._groups if group.group_id == group_id), None
        )

    @staticmethod
    def _change_payload(
        change_id: str,
        group_id: str,
        changes: dict,
    ) -> dict:
        change = changes[change_id]
        return {
            "changeId": change_id,
            "groupId": group_id,
            "path": change.path,
            "status": change.status,
            "staged": change.staged,
            "additions": change.additions,
            "deletions": change.deletions,
            "binary": change.binary,
            "truncated": change.truncated,
            "unsupportedReason": change.unsupported_reason,
        }
