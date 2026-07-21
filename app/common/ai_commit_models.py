# coding: utf-8
"""AI 提交规划器的结构化协议与确定性校验。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "1"
PLAN_LEVELS = {"file", "hunk"}


class PlanProtocolError(ValueError):
    """模型响应不符合结构化协议。"""


def _strict_keys(data: Mapping[str, Any], allowed: set[str], context: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise PlanProtocolError(f"{context} 包含未知字段: {', '.join(unknown)}")


def _require_string(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise PlanProtocolError(f"{context}.{key} 必须是字符串")
    return value


def _string_list(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise PlanProtocolError(f"{context} 必须是字符串数组")
    return tuple(value)


@dataclass(frozen=True)
class HunkChange:
    change_id: str
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    additions: int
    deletions: int
    content: str

    def to_prompt_payload(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "header": self.header,
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "additions": self.additions,
            "deletions": self.deletions,
            "content": self.content,
        }


@dataclass(frozen=True)
class FileChangeSnapshot:
    change_id: str
    path: str
    old_path: str
    new_path: str
    status: str
    staged: bool
    binary: bool
    truncated: bool
    unsupported_reason: str
    additions: int
    deletions: int
    patch: str
    hunks: tuple[HunkChange, ...] = ()

    @property
    def executable(self) -> bool:
        return not self.truncated and not self.unsupported_reason

    def expected_ids(self, level: str) -> tuple[str, ...]:
        if level == "hunk" and self.hunks:
            return tuple(hunk.change_id for hunk in self.hunks)
        return (self.change_id,)

    def to_prompt_payload(self, level: str = "file") -> dict[str, Any]:
        include_hunk_content = level == "hunk"
        return {
            "change_id": self.change_id,
            "path": self.path,
            "old_path": self.old_path,
            "new_path": self.new_path,
            "status": self.status,
            "staged": self.staged,
            "binary": self.binary,
            "truncated": self.truncated,
            "unsupported_reason": self.unsupported_reason,
            "additions": self.additions,
            "deletions": self.deletions,
            "patch": "" if include_hunk_content and self.hunks else self.patch,
            "hunks": [
                {
                    **hunk.to_prompt_payload(),
                    "content": hunk.content if include_hunk_content else "",
                }
                for hunk in self.hunks
            ],
        }


@dataclass(frozen=True)
class ChangeSnapshot:
    snapshot_id: str
    workspace_fingerprint: str
    repository_token: str
    head: str
    branch: str
    include_unstaged: bool
    complete: bool
    changes: tuple[FileChangeSnapshot, ...]
    recent_titles: tuple[str, ...] = ()
    instructions: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

    def expected_ids(self, level: str) -> tuple[str, ...]:
        if level not in PLAN_LEVELS:
            raise ValueError(f"不支持的规划级别: {level}")
        return tuple(
            change_id
            for change in self.changes
            for change_id in change.expected_ids(level)
        )

    def change_by_id(self, level: str) -> dict[str, FileChangeSnapshot]:
        result: dict[str, FileChangeSnapshot] = {}
        for change in self.changes:
            for change_id in change.expected_ids(level):
                result[change_id] = change
        return result

    def to_prompt_payload(self, level: str = "file") -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "head": self.head,
            "branch": self.branch,
            "include_unstaged": self.include_unstaged,
            "complete": self.complete,
            "changes": [change.to_prompt_payload(level) for change in self.changes],
            "recent_titles": list(self.recent_titles),
            "instructions": [
                {"name": name, "content": content}
                for name, content in self.instructions
            ],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class PlannerRequest:
    snapshot: ChangeSnapshot
    mode: str
    level: str
    generate_body: bool = True

    def to_prompt_payload(self) -> dict[str, Any]:
        if self.level not in PLAN_LEVELS:
            raise ValueError(f"不支持的规划级别: {self.level}")
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "level": self.level,
            "generate_body": self.generate_body,
            "snapshot": self.snapshot.to_prompt_payload(self.level),
        }


@dataclass(frozen=True)
class CommitGroup:
    group_id: str
    title: str
    body: str
    change_ids: tuple[str, ...]
    depends_on: tuple[str, ...]
    rationale: str
    warnings: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], index: int) -> "CommitGroup":
        context = f"groups[{index}]"
        _strict_keys(
            data,
            {
                "group_id", "title", "body", "change_ids",
                "depends_on", "rationale", "warnings",
            },
            context,
        )
        return cls(
            group_id=_require_string(data, "group_id", context),
            title=_require_string(data, "title", context),
            body=_require_string(data, "body", context),
            change_ids=_string_list(data.get("change_ids"), f"{context}.change_ids"),
            depends_on=_string_list(data.get("depends_on"), f"{context}.depends_on"),
            rationale=_require_string(data, "rationale", context),
            warnings=_string_list(data.get("warnings"), f"{context}.warnings"),
        )


@dataclass(frozen=True)
class CommitPlan:
    schema_version: str
    snapshot_id: str
    level: str
    summary: str
    groups: tuple[CommitGroup, ...]
    unassigned_change_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CommitPlan":
        if not isinstance(data, Mapping):
            raise PlanProtocolError("模型响应必须是对象")
        _strict_keys(
            data,
            {
                "schema_version", "snapshot_id", "level", "summary",
                "groups", "unassigned_change_ids", "warnings",
            },
            "plan",
        )
        raw_groups = data.get("groups")
        if not isinstance(raw_groups, list) or any(
            not isinstance(item, Mapping) for item in raw_groups
        ):
            raise PlanProtocolError("plan.groups 必须是对象数组")
        return cls(
            schema_version=_require_string(data, "schema_version", "plan"),
            snapshot_id=_require_string(data, "snapshot_id", "plan"),
            level=_require_string(data, "level", "plan"),
            summary=_require_string(data, "summary", "plan"),
            groups=tuple(
                CommitGroup.from_mapping(group, index)
                for index, group in enumerate(raw_groups)
            ),
            unassigned_change_ids=_string_list(
                data.get("unassigned_change_ids"), "plan.unassigned_change_ids"
            ),
            warnings=_string_list(data.get("warnings"), "plan.warnings"),
        )


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class PlanValidationResult:
    valid: bool
    executable: bool
    ordered_group_ids: tuple[str, ...]
    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)


class CommitPlanValidator:
    """只根据可信快照验证模型计划，不猜测或修补模型输出。"""

    def validate(
        self, plan: CommitPlan, snapshot: ChangeSnapshot
    ) -> PlanValidationResult:
        issues: list[ValidationIssue] = []
        if plan.schema_version != SCHEMA_VERSION:
            issues.append(ValidationIssue("schema_version", "不支持的协议版本"))
        if plan.snapshot_id != snapshot.snapshot_id:
            issues.append(ValidationIssue("snapshot_mismatch", "计划不属于当前快照"))
        if plan.level not in PLAN_LEVELS:
            issues.append(ValidationIssue("level", "不支持的规划级别"))
            expected: set[str] = set()
        else:
            expected = set(snapshot.expected_ids(plan.level))

        group_ids = [group.group_id for group in plan.groups]
        duplicate_groups = self._duplicates(group_ids)
        if duplicate_groups:
            issues.append(ValidationIssue("duplicate_group", "提交组标识重复"))

        assigned = [item for group in plan.groups for item in group.change_ids]
        duplicate_changes = self._duplicates(assigned)
        duplicate_unassigned = self._duplicates(plan.unassigned_change_ids)
        if duplicate_changes or duplicate_unassigned:
            issues.append(ValidationIssue("duplicate_change", "存在重复分配的改动"))
        unknown = (set(assigned) | set(plan.unassigned_change_ids)) - expected
        if unknown:
            issues.append(ValidationIssue("unknown_change", "计划引用了未知改动"))
        uncovered = expected - set(assigned) - set(plan.unassigned_change_ids)
        if uncovered:
            issues.append(ValidationIssue("missing_change", "计划遗漏了改动"))
        if set(assigned) & set(plan.unassigned_change_ids):
            issues.append(ValidationIssue("assigned_and_unassigned", "改动同时处于已分配和未分配状态"))

        known_groups = set(group_ids)
        for group in plan.groups:
            if not group.group_id.strip():
                issues.append(ValidationIssue("empty_group_id", "提交组标识不能为空"))
            if not group.title.strip() or self._has_control_character(group.title):
                issues.append(ValidationIssue("invalid_title", "提交标题为空或包含控制字符"))
            if not group.change_ids:
                issues.append(ValidationIssue("empty_group", "提交组没有改动"))
            if group.group_id in group.depends_on:
                issues.append(ValidationIssue("self_dependency", "提交组不能依赖自身"))
            if set(group.depends_on) - known_groups:
                issues.append(ValidationIssue("unknown_dependency", "提交组依赖未知组"))

        ordered = self._topological_order(plan.groups)
        if len(ordered) != len(plan.groups):
            issues.append(ValidationIssue("dependency_cycle", "提交组依赖存在循环"))

        structural_errors = [issue for issue in issues if issue.severity == "error"]
        valid = not structural_errors
        executable = valid and snapshot.complete and not plan.unassigned_change_ids
        if not snapshot.complete:
            issues.append(ValidationIssue("incomplete_snapshot", "快照内容不完整，只能查看计划", "warning"))
        if plan.level in PLAN_LEVELS:
            by_id = snapshot.change_by_id(plan.level)
            unsupported = {
                change_id for change_id in assigned
                if change_id in by_id and not by_id[change_id].executable
            }
            if unsupported:
                executable = False
                issues.append(ValidationIssue("unsupported_change", "计划包含不可自动执行的改动", "warning"))
        return PlanValidationResult(valid, executable, tuple(ordered), tuple(issues))

    @staticmethod
    def _duplicates(values: Sequence[str]) -> set[str]:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for value in values:
            if value in seen:
                duplicates.add(value)
            else:
                seen.add(value)
        return duplicates

    @staticmethod
    def _has_control_character(value: str) -> bool:
        return any(ord(char) < 32 or ord(char) == 127 for char in value)

    @staticmethod
    def _topological_order(groups: Sequence[CommitGroup]) -> list[str]:
        remaining = {group.group_id: set(group.depends_on) for group in groups}
        ordered: list[str] = []
        while remaining:
            ready = [group_id for group_id, deps in remaining.items() if not deps]
            if not ready:
                break
            for group_id in ready:
                ordered.append(group_id)
                remaining.pop(group_id)
            for deps in remaining.values():
                deps.difference_update(ready)
        return ordered
