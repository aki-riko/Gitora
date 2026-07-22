# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.ai_commit_context import ChangeContextCollector
from app.common.ai_commit_executor import FilePlanExecutor, PlanExecutionError
from app.common.ai_commit_models import CommitPlan, CommitPlanValidator
from app.common.ai_commit_settings import AiCommitSettingsStore
from app.common.git_service import GitService
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class FilePlanExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = init_repo(Path(self.temp_dir.name) / "repo")
        write_file(self.repo, "a.txt", "base a\n")
        write_file(self.repo, "b.txt", "base b\n")
        commit_all(self.repo, "chore: base")
        self.service = GitService()
        self.assertTrue(self.service.set_repo_path(str(self.repo), emit_status=False))
        self.settings = AiCommitSettingsStore(
            DEFAULTS, Path(self.temp_dir.name) / "settings.json"
        ).load()

    def make_snapshot_and_plan(self):
        snapshot = ChangeContextCollector(
            self.service, self.settings.limits
        ).collect(str(self.repo), include_unstaged=True)
        ids_by_path = {change.path: change.change_id for change in snapshot.changes}
        plan = CommitPlan.from_mapping({
            "schema_version": "1",
            "snapshot_id": snapshot.snapshot_id,
            "level": "file",
            "summary": "拆分两个文件",
            "groups": [
                {
                    "group_id": "first",
                    "title": "feat: 更新 a",
                    "body": "",
                    "change_ids": [ids_by_path["a.txt"]],
                    "depends_on": [],
                    "rationale": "先更新 a",
                    "warnings": [],
                },
                {
                    "group_id": "second",
                    "title": "feat: 更新 b",
                    "body": "",
                    "change_ids": [ids_by_path["b.txt"]],
                    "depends_on": ["first"],
                    "rationale": "再更新 b",
                    "warnings": [],
                },
            ],
            "unassigned_change_ids": [],
            "warnings": [],
        })
        validation = CommitPlanValidator().validate(
            plan, snapshot, expected_level="file"
        )
        return snapshot, plan, validation

    def test_failed_stage_restores_exact_original_index_tree(self) -> None:
        write_file(self.repo, "a.txt", "changed a\n")
        write_file(self.repo, "b.txt", "changed b\n")
        run_git(self.repo, "add", "a.txt", "b.txt")
        snapshot, plan, validation = self.make_snapshot_and_plan()
        before_tree = run_git(self.repo, "write-tree").stdout.strip()
        before_diff = run_git(self.repo, "diff", "--cached").stdout
        original_run = self.service._run_git_sync_at

        def fail_target_add(repo_path, args, timeout=30):
            if args[:3] == ["--literal-pathspecs", "add", "-A"]:
                return False, "", "injected add failure"
            return original_run(repo_path, args, timeout)

        self.service._run_git_sync_at = fail_target_add
        try:
            with self.assertRaisesRegex(PlanExecutionError, "injected add failure"):
                FilePlanExecutor(self.service).apply_next(
                    str(self.repo),
                    snapshot,
                    plan,
                    validation,
                    False,
                    self.settings.limits,
                )
        finally:
            self.service._run_git_sync_at = original_run

        self.assertEqual(run_git(self.repo, "write-tree").stdout.strip(), before_tree)
        self.assertEqual(run_git(self.repo, "diff", "--cached").stdout, before_diff)

    def test_rename_with_spaces_is_staged_without_absorbing_other_changes(self) -> None:
        write_file(self.repo, "旧 名称.txt", "rename me\n")
        write_file(self.repo, "删除.txt", "delete me\n")
        commit_all(self.repo, "test: add path fixtures")
        run_git(self.repo, "mv", "旧 名称.txt", "新 名称.txt")
        (self.repo / "删除.txt").unlink()
        write_file(self.repo, "额外.txt", "new file\n")
        snapshot = ChangeContextCollector(
            self.service, self.settings.limits
        ).collect(str(self.repo), include_unstaged=True)
        renamed = next(change for change in snapshot.changes if change.status == "R")
        remaining = [
            change.change_id for change in snapshot.changes
            if change.change_id != renamed.change_id
        ]
        plan = CommitPlan.from_mapping({
            "schema_version": "1",
            "snapshot_id": snapshot.snapshot_id,
            "level": "file",
            "summary": "路径矩阵",
            "groups": [
                {
                    "group_id": "rename",
                    "title": "refactor: 重命名文件",
                    "body": "",
                    "change_ids": [renamed.change_id],
                    "depends_on": [],
                    "rationale": "独立重命名",
                    "warnings": [],
                },
                {
                    "group_id": "remaining",
                    "title": "chore: 处理其余路径",
                    "body": "",
                    "change_ids": remaining,
                    "depends_on": ["rename"],
                    "rationale": "其余改动",
                    "warnings": [],
                },
            ],
            "unassigned_change_ids": [],
            "warnings": [],
        })
        validation = CommitPlanValidator().validate(plan, snapshot, "file")

        FilePlanExecutor(self.service).apply_next(
            str(self.repo), snapshot, plan, validation, False, self.settings.limits
        )

        staged = {
            change.path for change in self.service.get_status_at(str(self.repo))
            if change.staged
        }
        self.assertEqual(staged, {renamed.path})
        self.assertIn("删除.txt", run_git(self.repo, "status", "--porcelain=v1").stdout)
        self.assertIn("额外.txt", run_git(self.repo, "status", "--porcelain=v1").stdout)

    def test_staged_only_plan_rejects_unplanned_worktree_path(self) -> None:
        write_file(self.repo, "a.txt", "changed a\n")
        run_git(self.repo, "add", "a.txt")
        write_file(self.repo, "b.txt", "changed b\n")
        snapshot = ChangeContextCollector(
            self.service, self.settings.limits
        ).collect(str(self.repo), include_unstaged=False)
        change_id = snapshot.changes[0].change_id
        plan = CommitPlan.from_mapping({
            "schema_version": "1",
            "snapshot_id": snapshot.snapshot_id,
            "level": "file",
            "summary": "只规划暂存区",
            "groups": [{
                "group_id": "only",
                "title": "feat: 更新 a",
                "body": "",
                "change_ids": [change_id],
                "depends_on": [],
                "rationale": "只包含暂存区",
                "warnings": [],
            }],
            "unassigned_change_ids": [],
            "warnings": [],
        })
        validation = CommitPlanValidator().validate(plan, snapshot, "file")

        with self.assertRaisesRegex(PlanExecutionError, "未纳入计划"):
            FilePlanExecutor(self.service).apply_next(
                str(self.repo), snapshot, plan, validation, False, self.settings.limits
            )

    def test_restore_refuses_to_overwrite_index_after_head_changes(self) -> None:
        write_file(self.repo, "a.txt", "changed a\n")
        write_file(self.repo, "b.txt", "changed b\n")
        snapshot, plan, validation = self.make_snapshot_and_plan()
        executor = FilePlanExecutor(self.service)
        applied = executor.apply_next(
            str(self.repo), snapshot, plan, validation, False, self.settings.limits
        )
        committed, message = self.service.commit(applied.group.title)
        self.assertTrue(committed, message)

        restored, restore_message = executor.restore_uncommitted_group(applied)

        self.assertFalse(restored)
        self.assertIn("HEAD 已变化", restore_message)
        self.assertEqual(run_git(self.repo, "diff", "--cached").stdout, "")


if __name__ == "__main__":
    unittest.main()
