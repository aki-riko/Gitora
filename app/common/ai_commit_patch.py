# coding: utf-8
"""代码块计划的补丁构造与隔离索引试应用。"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .ai_commit_context import ChangeContextCollector, SnapshotLimits
from .ai_commit_models import (
    ChangeSnapshot,
    CommitGroup,
    CommitPlan,
    FileChangeSnapshot,
    PlanValidationResult,
)
from .git_service import GitService


class PatchValidationError(RuntimeError):
    """补丁无法构造、试应用失败或联合树不完整。"""


@dataclass(frozen=True)
class BuiltGroupPatch:
    group_id: str
    patch: str
    whole_file_change_ids: tuple[str, ...]


@dataclass(frozen=True)
class TemporaryPlanResult:
    group_trees: tuple[tuple[str, str], ...]
    expected_tree: str


class HunkPatchBuilder:
    """只从可信快照拼接文件头和已选择 hunk，不解析模型自然语言。"""

    @classmethod
    def build_group(
        cls, snapshot: ChangeSnapshot, group: CommitGroup
    ) -> BuiltGroupPatch:
        selected = set(group.change_ids)
        expected = set(snapshot.expected_ids("hunk"))
        unknown = selected - expected
        if unknown:
            raise PatchValidationError("提交组引用了未知代码块")
        sections: list[str] = []
        whole_file_ids: list[str] = []
        for change in snapshot.changes:
            assigned = selected & set(change.expected_ids("hunk"))
            if not assigned:
                continue
            section, whole_file_id = cls._build_change(change, assigned)
            if section:
                sections.append(section)
            if whole_file_id:
                whole_file_ids.append(whole_file_id)
        return BuiltGroupPatch(
            group.group_id,
            "".join(sections),
            tuple(whole_file_ids),
        )

    @classmethod
    def _build_change(
        cls, change: FileChangeSnapshot, assigned: set[str]
    ) -> tuple[str, str]:
        if not change.hunks:
            if assigned != {change.change_id}:
                raise PatchValidationError("整文件改动的标识不一致")
            if change.patch.startswith("diff --git "):
                return cls._metadata_patch(change), ""
            return "", change.change_id
        hunk_by_id = {hunk.change_id: hunk for hunk in change.hunks}
        ordered = [
            hunk_by_id[hunk.change_id].content
            for hunk in change.hunks
            if hunk.change_id in assigned
        ]
        if len(ordered) != len(assigned):
            raise PatchValidationError("代码块不属于对应文件")
        section = cls._file_header(change.patch) + "".join(ordered)
        return (section if section.endswith("\n") else section + "\n"), ""

    @staticmethod
    def _file_header(raw_patch: str) -> str:
        lines = raw_patch.splitlines(keepends=True)
        first_hunk = next(
            (index for index, line in enumerate(lines) if line.startswith("@@ ")),
            -1,
        )
        if first_hunk <= 0:
            raise PatchValidationError("文件差异缺少可用的统一补丁头")
        header = "".join(lines[:first_hunk])
        return header if header.endswith("\n") else header + "\n"

    @staticmethod
    def _metadata_patch(change: FileChangeSnapshot) -> str:
        patch = change.patch if change.patch.endswith("\n") else change.patch + "\n"
        if "\n--- " in patch or "\nrename from " in patch:
            return patch
        old_path = change.old_path or change.path
        new_path = change.new_path or change.path
        old_marker = "/dev/null" if change.status == "A" else f"a/{old_path}"
        new_marker = "/dev/null" if change.status == "D" else f"b/{new_path}"
        return patch + f"--- {old_marker}\n+++ {new_marker}\n"


class TemporaryIndexValidator:
    """在 GIT_INDEX_FILE 指向的隔离索引内按组试应用并比较最终树。"""

    def __init__(self, git_service: GitService):
        self._git = git_service

    def validate(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        plan: CommitPlan,
        validation: PlanValidationResult,
        limits: SnapshotLimits,
        timeout_seconds: int,
    ) -> TemporaryPlanResult:
        collector, before_fingerprint, before_tree = self._validate_context(
            repo_path, snapshot, plan, validation, limits
        )
        built_groups = [
            HunkPatchBuilder.build_group(snapshot, group) for group in plan.groups
        ]
        with tempfile.TemporaryDirectory(prefix="gitora-ai-index-") as temp_dir:
            group_trees, expected_tree = self._validate_in_temporary_indexes(
                repo_path, snapshot, built_groups, before_tree,
                Path(temp_dir), timeout_seconds,
            )
        self._ensure_real_state_unchanged(
            repo_path, collector, before_fingerprint, before_tree
        )
        return TemporaryPlanResult(tuple(group_trees), expected_tree)

    def _validate_context(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        plan: CommitPlan,
        validation: PlanValidationResult,
        limits: SnapshotLimits,
    ) -> tuple[ChangeContextCollector, str, str]:
        if plan.level != "hunk":
            raise PatchValidationError("临时索引试应用只接受代码块级计划")
        if not validation.valid or not validation.executable:
            raise PatchValidationError("代码块计划未通过覆盖校验")
        if repo_path != (self._git.repo_path or ""):
            raise PatchValidationError("当前仓库与代码块计划不一致")
        collector = ChangeContextCollector(self._git, limits)
        before_fingerprint = collector.workspace_fingerprint(repo_path)
        if before_fingerprint != snapshot.workspace_fingerprint:
            raise PatchValidationError("工作区已变化，请重新规划")
        return collector, before_fingerprint, self._real_index_tree(repo_path)

    def _validate_in_temporary_indexes(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        built_groups: list[BuiltGroupPatch],
        before_tree: str,
        base: Path,
        timeout_seconds: int,
    ) -> tuple[list[tuple[str, str]], str]:
        plan_env = self._index_environment(base / "plan.index")
        self._initialize_index(repo_path, snapshot.head, plan_env, timeout_seconds)
        group_trees = self._apply_groups(
            repo_path, snapshot, built_groups, plan_env, timeout_seconds
        )
        expected_tree = self._expected_tree(
            repo_path, snapshot, before_tree, base, timeout_seconds
        )
        if not group_trees or group_trees[-1][1] != expected_tree:
            raise PatchValidationError("所有提交组联合后未完整覆盖工作区目标树")
        return group_trees, expected_tree

    def _apply_groups(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        built_groups: list[BuiltGroupPatch],
        plan_env: dict[str, str],
        timeout_seconds: int,
    ) -> list[tuple[str, str]]:
        by_id = snapshot.change_by_id("hunk")
        group_trees: list[tuple[str, str]] = []
        for built in built_groups:
            IndexPatchApplier.apply_group(
                repo_path, built, by_id, plan_env, timeout_seconds
            )
            group_trees.append((
                built.group_id,
                self._write_tree(repo_path, plan_env, timeout_seconds),
            ))
        return group_trees

    def _expected_tree(
        self,
        repo_path: str,
        snapshot: ChangeSnapshot,
        before_tree: str,
        base: Path,
        timeout_seconds: int,
    ) -> str:
        if not snapshot.include_unstaged:
            return before_tree
        worktree_paths = self._deduplicate([
            path
            for change in snapshot.changes
            if not change.staged
            for path in self._paths_for_change(change)
        ])
        if not worktree_paths:
            return before_tree
        expected_env = self._index_environment(base / "expected.index")
        self._initialize_index(repo_path, before_tree, expected_env, timeout_seconds)
        self._run_required(
            repo_path,
            ["add", "-A", "--", *worktree_paths],
            expected_env,
            timeout_seconds,
            "无法构造工作区目标树",
        )
        return self._write_tree(repo_path, expected_env, timeout_seconds)

    def _ensure_real_state_unchanged(
        self,
        repo_path: str,
        collector: ChangeContextCollector,
        before_fingerprint: str,
        before_tree: str,
    ) -> None:
        after_tree = self._real_index_tree(repo_path)
        after_fingerprint = collector.workspace_fingerprint(repo_path)
        if after_tree != before_tree or after_fingerprint != before_fingerprint:
            raise PatchValidationError("临时索引验证意外改变了真实仓库状态")

    def _real_index_tree(self, repo_path: str) -> str:
        ok, tree, error = self._git._run_git_sync_at(  # noqa: SLF001
            repo_path, ["write-tree"]
        )
        if not ok or not tree.strip():
            raise PatchValidationError(error.strip() or "无法读取真实索引树")
        return tree.strip()

    @classmethod
    def _initialize_index(
        cls,
        repo_path: str,
        head: str,
        environment: dict[str, str],
        timeout_seconds: int,
    ) -> None:
        args = ["read-tree", head] if head else ["read-tree", "--empty"]
        cls._run_required(
            repo_path, args, environment, timeout_seconds, "无法初始化临时索引"
        )

    @classmethod
    def _write_tree(
        cls,
        repo_path: str,
        environment: dict[str, str],
        timeout_seconds: int,
    ) -> str:
        output = cls._run_required(
            repo_path,
            ["write-tree"],
            environment,
            timeout_seconds,
            "无法写出临时索引树",
        )
        return output.strip()

    @staticmethod
    def _index_environment(index_path: Path) -> dict[str, str]:
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(index_path.resolve())
        return environment

    @staticmethod
    def _run_required(
        repo_path: str,
        args: list[str],
        environment: dict[str, str],
        timeout_seconds: int,
        fallback: str,
        input_text: str | None = None,
    ) -> str:
        try:
            result = TemporaryIndexValidator._run_process(
                repo_path, args, environment, timeout_seconds, input_text
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise PatchValidationError(
                f"{fallback}（{type(exc).__name__}）"
            ) from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise PatchValidationError(detail[-1000:] if detail else fallback)
        return result.stdout

    @staticmethod
    def _run_process(
        repo_path: str,
        args: list[str],
        environment: dict[str, str],
        timeout_seconds: int,
        input_text: str | None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "git", "--literal-pathspecs", "-c", "core.quotepath=false", *args,
        ]
        return subprocess.run(
            command,
            cwd=repo_path,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    @staticmethod
    def _paths_for_change(change: FileChangeSnapshot) -> list[str]:
        return [
            path for path in (change.path, change.old_path, change.new_path) if path
        ]

    @staticmethod
    def _deduplicate(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))


class IndexPatchApplier:
    """把可信构造结果写入指定索引；调用方决定是真实还是隔离索引。"""

    @classmethod
    def apply_group(
        cls,
        repo_path: str,
        built: BuiltGroupPatch,
        by_id: dict,
        environment: dict[str, str],
        timeout_seconds: int,
    ) -> None:
        cls._apply_whole_files(
            repo_path, built, by_id, environment, timeout_seconds
        )
        cls._apply_patch(
            repo_path, built, environment, timeout_seconds
        )

    @staticmethod
    def _apply_whole_files(
        repo_path: str,
        built: BuiltGroupPatch,
        by_id: dict,
        environment: dict[str, str],
        timeout_seconds: int,
    ) -> None:
        whole_paths = []
        for change_id in built.whole_file_change_ids:
            change = by_id[change_id]
            whole_paths.extend(TemporaryIndexValidator._paths_for_change(change))
        if whole_paths:
            TemporaryIndexValidator._run_required(
                repo_path,
                [
                    "add", "-A", "--",
                    *TemporaryIndexValidator._deduplicate(whole_paths),
                ],
                environment,
                timeout_seconds,
                f"提交组 {built.group_id} 的整文件暂存试应用失败",
            )

    @staticmethod
    def _apply_patch(
        repo_path: str,
        built: BuiltGroupPatch,
        environment: dict[str, str],
        timeout_seconds: int,
    ) -> None:
        if built.patch:
            TemporaryIndexValidator._run_required(
                repo_path,
                ["apply", "--cached", "--check", "--whitespace=nowarn", "-"],
                environment,
                timeout_seconds,
                f"提交组 {built.group_id} 的补丁检查失败",
                built.patch,
            )
            TemporaryIndexValidator._run_required(
                repo_path,
                ["apply", "--cached", "--whitespace=nowarn", "-"],
                environment,
                timeout_seconds,
                f"提交组 {built.group_id} 的补丁试应用失败",
                built.patch,
            )
