# coding: utf-8
"""代码块计划在逐组提交后的确定性重映射。"""
from __future__ import annotations

from dataclasses import dataclass

from .ai_commit_models import (
    ChangeSnapshot,
    CommitGroup,
    CommitPlan,
    FileChangeSnapshot,
)


@dataclass(frozen=True)
class HunkRemapResult:
    advanced: bool
    completed: bool
    message: str
    plan: CommitPlan | None = None


class HunkPlanRemapper:
    """按路径和 hunk 正文多重集映射，拒绝新增、遗漏或内容漂移。"""

    @classmethod
    def advance(
        cls,
        old_snapshot: ChangeSnapshot,
        fresh_snapshot: ChangeSnapshot,
        plan: CommitPlan,
        completed_group_id: str,
    ) -> HunkRemapResult:
        if plan.level != "hunk" or not plan.groups:
            return HunkRemapResult(False, False, "没有可推进的代码块计划")
        if plan.groups[0].group_id != completed_group_id:
            return HunkRemapResult(False, False, "已提交组与计划顺序不一致")
        remaining_groups = plan.groups[1:]
        if not remaining_groups:
            return cls._finish_result(fresh_snapshot)
        remaining_ids = [
            change_id
            for group in remaining_groups
            for change_id in group.change_ids
        ]
        mapping, message = cls._map_remaining_ids(
            old_snapshot, fresh_snapshot, remaining_ids
        )
        if mapping is None:
            return HunkRemapResult(False, False, message)
        remapped = cls._build_remapped_plan(
            plan, fresh_snapshot, completed_group_id, mapping
        )
        return HunkRemapResult(
            True, False, "已推进到下一代码块组", remapped
        )

    @staticmethod
    def _finish_result(fresh_snapshot: ChangeSnapshot) -> HunkRemapResult:
        if fresh_snapshot.changes:
            return HunkRemapResult(
                False, False, "最后一组提交后仍有新改动，请重新规划"
            )
        return HunkRemapResult(True, True, "全部计划组已完成")

    @classmethod
    def _map_remaining_ids(
        cls,
        old_snapshot: ChangeSnapshot,
        fresh_snapshot: ChangeSnapshot,
        remaining_ids: list[str],
    ) -> tuple[dict[str, str] | None, str]:
        if len(remaining_ids) != len(fresh_snapshot.expected_ids("hunk")):
            return None, "提交后代码块数量与剩余计划不一致"
        old_by_id = old_snapshot.change_by_id("hunk")
        fresh_by_id = fresh_snapshot.change_by_id("hunk")
        fresh_buckets: dict[tuple, list[str]] = {}
        for change_id in fresh_snapshot.expected_ids("hunk"):
            key = cls._remap_key(fresh_by_id[change_id], change_id)
            fresh_buckets.setdefault(key, []).append(change_id)
        new_id_by_old: dict[str, str] = {}
        for change_id in remaining_ids:
            change = old_by_id.get(change_id)
            if change is None:
                return None, "剩余代码块不属于原计划"
            candidates = fresh_buckets.get(cls._remap_key(change, change_id), [])
            if not candidates:
                return None, f"{change.path} 的剩余代码块发生变化"
            new_id_by_old[change_id] = candidates.pop(0)
        if any(fresh_buckets.values()):
            return None, "提交后出现计划外代码块，请重新规划"
        return new_id_by_old, ""

    @staticmethod
    def _build_remapped_plan(
        plan: CommitPlan,
        fresh_snapshot: ChangeSnapshot,
        completed_group_id: str,
        new_id_by_old: dict[str, str],
    ) -> CommitPlan:
        return CommitPlan(
            schema_version=plan.schema_version,
            snapshot_id=fresh_snapshot.snapshot_id,
            level="hunk",
            summary=plan.summary,
            groups=tuple(
                CommitGroup(
                    group.group_id,
                    group.title,
                    group.body,
                    tuple(new_id_by_old[item] for item in group.change_ids),
                    tuple(
                        item for item in group.depends_on
                        if item != completed_group_id
                    ),
                    group.rationale,
                    group.warnings,
                )
                for group in plan.groups[1:]
            ),
            unassigned_change_ids=(),
            warnings=plan.warnings,
        )

    @staticmethod
    def _remap_key(change: FileChangeSnapshot, change_id: str) -> tuple:
        hunk = next(
            (item for item in change.hunks if item.change_id == change_id), None
        )
        if hunk is not None:
            body = hunk.content.split("\n", 1)[1] if "\n" in hunk.content else ""
            return "hunk", change.path, body
        return (
            "file",
            change.path,
            change.old_path,
            change.new_path,
            change.status,
            change.binary,
            change.truncated,
            change.unsupported_reason,
            change.patch,
        )
