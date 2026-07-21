# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.ai_commit_context import ChangeContextCollector
from app.common.ai_commit_models import CommitPlan, CommitPlanValidator
from app.common.ai_commit_patch import HunkPatchBuilder, TemporaryIndexValidator
from app.common.ai_commit_settings import AiCommitSettingsStore
from app.common.git_service import GitService
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class HunkPatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = init_repo(Path(self.temp_dir.name) / "repo")
        self.base_lines = [f"line {index}\n" for index in range(1, 41)]
        write_file(self.repo, "code.txt", "".join(self.base_lines))
        commit_all(self.repo, "chore: base")
        self.service = GitService()
        self.assertTrue(self.service.set_repo_path(str(self.repo), emit_status=False))
        self.settings = AiCommitSettingsStore(
            DEFAULTS, Path(self.temp_dir.name) / "settings.json"
        ).load()

    def collect(self):
        return ChangeContextCollector(
            self.service, self.settings.limits
        ).collect(str(self.repo), include_unstaged=True)

    @staticmethod
    def plan_for(snapshot, grouped_ids: list[list[str]]) -> CommitPlan:
        return CommitPlan.from_mapping({
            "schema_version": "1",
            "snapshot_id": snapshot.snapshot_id,
            "level": "hunk",
            "summary": "按代码块拆分",
            "groups": [
                {
                    "group_id": f"group-{index + 1}",
                    "title": f"feat: 代码块 {index + 1}",
                    "body": "",
                    "change_ids": change_ids,
                    "depends_on": [] if index == 0 else [f"group-{index}"],
                    "rationale": "独立代码块",
                    "warnings": [],
                }
                for index, change_ids in enumerate(grouped_ids)
            ],
            "unassigned_change_ids": [],
            "warnings": [],
        })

    def test_two_hunks_apply_in_temporary_index_without_real_index_writes(self) -> None:
        changed = list(self.base_lines)
        changed[1] = "changed near top\n"
        changed[34] = "changed near bottom\n"
        write_file(self.repo, "code.txt", "".join(changed))
        write_file(self.repo, "新增 文件.txt", "whole file\n")
        snapshot = self.collect()
        code = next(change for change in snapshot.changes if change.path == "code.txt")
        added = next(change for change in snapshot.changes if change.path == "新增 文件.txt")
        self.assertEqual(len(code.hunks), 2)
        plan = self.plan_for(snapshot, [
            [code.hunks[0].change_id],
            [code.hunks[1].change_id],
            [added.change_id],
        ])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")
        before_tree = run_git(self.repo, "write-tree").stdout.strip()
        before_status = run_git(self.repo, "status", "--porcelain=v1", "-uall").stdout

        first_patch = HunkPatchBuilder.build_group(snapshot, plan.groups[0])
        self.assertIn("changed near top", first_patch.patch)
        self.assertNotIn("changed near bottom", first_patch.patch)
        result = TemporaryIndexValidator(self.service).validate(
            str(self.repo),
            snapshot,
            plan,
            validation,
            self.settings.limits,
            self.settings.timeout_seconds,
        )

        self.assertEqual(len(result.group_trees), 3)
        self.assertEqual(run_git(self.repo, "write-tree").stdout.strip(), before_tree)
        self.assertEqual(
            run_git(self.repo, "status", "--porcelain=v1", "-uall").stdout,
            before_status,
        )

    def test_partially_staged_file_validates_staged_layer_before_unstaged(self) -> None:
        staged_lines = list(self.base_lines)
        staged_lines[1] = "staged top\n"
        write_file(self.repo, "code.txt", "".join(staged_lines))
        run_git(self.repo, "add", "code.txt")
        final_lines = list(staged_lines)
        final_lines[34] = "unstaged bottom\n"
        write_file(self.repo, "code.txt", "".join(final_lines))
        snapshot = self.collect()
        staged_change = next(change for change in snapshot.changes if change.staged)
        unstaged_change = next(change for change in snapshot.changes if not change.staged)
        plan = self.plan_for(snapshot, [
            [staged_change.hunks[0].change_id],
            [unstaged_change.hunks[0].change_id],
        ])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")
        before_tree = run_git(self.repo, "write-tree").stdout.strip()

        result = TemporaryIndexValidator(self.service).validate(
            str(self.repo),
            snapshot,
            plan,
            validation,
            self.settings.limits,
            self.settings.timeout_seconds,
        )

        self.assertEqual(len(result.group_trees), 2)
        self.assertEqual(run_git(self.repo, "write-tree").stdout.strip(), before_tree)

    def test_identical_staged_and_unstaged_hunks_apply_as_separate_groups(self) -> None:
        block = (
            "".join(f"ctx {index}\n" for index in range(1, 5))
            + "target\n"
            + "".join(f"ctx {index}\n" for index in range(5, 9))
        )
        write_file(self.repo, "same.txt", block + "separator\n" * 10 + block)
        commit_all(self.repo, "chore: duplicate hunk base")
        base = (self.repo / "same.txt").read_text(encoding="utf-8")
        staged = base.replace("target\n", "changed\n", 1)
        write_file(self.repo, "same.txt", staged)
        run_git(self.repo, "add", "same.txt")
        second_position = staged.rfind("target\n")
        write_file(
            self.repo,
            "same.txt",
            staged[:second_position]
            + "changed\n"
            + staged[second_position + len("target\n"):],
        )
        snapshot = self.collect()
        staged_change = next(change for change in snapshot.changes if change.staged)
        unstaged_change = next(change for change in snapshot.changes if not change.staged)
        ids = [
            staged_change.hunks[0].change_id,
            unstaged_change.hunks[0].change_id,
        ]
        self.assertEqual(len(set(ids)), 2)
        plan = self.plan_for(snapshot, [[ids[0]], [ids[1]]])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")

        result = TemporaryIndexValidator(self.service).validate(
            str(self.repo),
            snapshot,
            plan,
            validation,
            self.settings.limits,
            self.settings.timeout_seconds,
        )

        self.assertEqual(len(result.group_trees), 2)
        self.assertEqual(result.group_trees[-1][1], result.expected_tree)


if __name__ == "__main__":
    unittest.main()
