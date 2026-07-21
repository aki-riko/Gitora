# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.common.ai_commit_context import ChangeContextCollector
from app.common.ai_commit_executor import HunkPlanExecutor, PlanExecutionError
from app.common.ai_commit_models import CommitPlan, CommitPlanValidator
from app.common.ai_commit_patch import IndexPatchApplier, PatchValidationError
from app.common.ai_commit_remap import HunkPlanRemapper
from app.common.ai_commit_settings import AiCommitSettingsStore
from app.common.git_service import GitService
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class HunkPlanExecutorTest(unittest.TestCase):
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
        self.executor = HunkPlanExecutor(self.service)

    def collect(self, include_unstaged: bool = True):
        return ChangeContextCollector(
            self.service, self.settings.limits
        ).collect(str(self.repo), include_unstaged)

    @staticmethod
    def plan_for(snapshot, grouped_ids: list[list[str]]) -> CommitPlan:
        return CommitPlan.from_mapping({
            "schema_version": "1",
            "snapshot_id": snapshot.snapshot_id,
            "level": "hunk",
            "summary": "逐组代码块计划",
            "groups": [
                {
                    "group_id": f"group-{index + 1}",
                    "title": f"feat: 代码块 {index + 1}",
                    "body": "",
                    "change_ids": ids,
                    "depends_on": [] if index == 0 else [f"group-{index}"],
                    "rationale": "独立代码块",
                    "warnings": [],
                }
                for index, ids in enumerate(grouped_ids)
            ],
            "unassigned_change_ids": [],
            "warnings": [],
        })

    def apply_and_commit(self, snapshot, plan):
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")
        applied = self.executor.apply_next(
            str(self.repo),
            snapshot,
            plan,
            validation,
            False,
            self.settings.limits,
            self.settings.timeout_seconds,
        )
        ok, message = self.service.commit(applied.group.title)
        self.assertTrue(ok, message)
        verified, _head = self.executor.verify_committed_group(applied)
        self.assertTrue(verified)
        fresh = self.collect()
        return fresh, HunkPlanRemapper.advance(
            snapshot, fresh, plan, applied.group.group_id
        )

    def test_same_file_hunks_and_untracked_file_commit_in_order(self) -> None:
        changed = list(self.base_lines)
        changed[1] = "changed top\n"
        changed[34] = "changed bottom\n"
        write_file(self.repo, "code.txt", "".join(changed))
        write_file(self.repo, "新增 文件.txt", "new file\n")
        snapshot = self.collect()
        code = next(change for change in snapshot.changes if change.path == "code.txt")
        added = next(change for change in snapshot.changes if change.path != "code.txt")
        plan = self.plan_for(snapshot, [
            [code.hunks[0].change_id],
            [code.hunks[1].change_id],
            [added.change_id],
        ])

        fresh, remapped = self.apply_and_commit(snapshot, plan)
        self.assertTrue(remapped.advanced)
        self.assertNotIn("changed top", run_git(self.repo, "diff").stdout)
        self.assertIn("changed bottom", run_git(self.repo, "diff").stdout)
        fresh, remapped = self.apply_and_commit(fresh, remapped.plan)
        self.assertTrue(remapped.advanced)
        fresh, remapped = self.apply_and_commit(fresh, remapped.plan)

        self.assertTrue(remapped.completed)
        self.assertEqual(fresh.changes, ())
        self.assertEqual(run_git(self.repo, "status", "--porcelain=v1").stdout, "")

    def test_real_apply_failure_restores_exact_original_index(self) -> None:
        changed = list(self.base_lines)
        changed[1] = "staged top\n"
        write_file(self.repo, "code.txt", "".join(changed))
        run_git(self.repo, "add", "code.txt")
        changed[34] = "unstaged bottom\n"
        write_file(self.repo, "code.txt", "".join(changed))
        snapshot = self.collect()
        plan = self.plan_for(snapshot, [
            [change.hunks[0].change_id] for change in snapshot.changes
        ])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")
        before_tree = run_git(self.repo, "write-tree").stdout.strip()
        before_cached = run_git(self.repo, "diff", "--cached").stdout
        original_apply = IndexPatchApplier.apply_group

        def fail_real(*args, **kwargs):
            environment = args[3]
            if "GIT_INDEX_FILE" not in environment:
                raise PatchValidationError("injected real apply failure")
            return original_apply(*args, **kwargs)

        with mock.patch.object(
            IndexPatchApplier, "apply_group", side_effect=fail_real
        ):
            with self.assertRaisesRegex(PlanExecutionError, "injected"):
                self.executor.apply_next(
                    str(self.repo), snapshot, plan, validation, False,
                    self.settings.limits, self.settings.timeout_seconds,
                )

        self.assertEqual(run_git(self.repo, "write-tree").stdout.strip(), before_tree)
        self.assertEqual(run_git(self.repo, "diff", "--cached").stdout, before_cached)

    def test_staged_only_hunk_does_not_absorb_unstaged_hunk(self) -> None:
        changed = list(self.base_lines)
        changed[1] = "staged top\n"
        write_file(self.repo, "code.txt", "".join(changed))
        run_git(self.repo, "add", "code.txt")
        changed[34] = "unstaged bottom\n"
        write_file(self.repo, "code.txt", "".join(changed))
        snapshot = self.collect(include_unstaged=False)
        plan = self.plan_for(snapshot, [[snapshot.expected_ids("hunk")[0]]])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")

        self.executor.apply_next(
            str(self.repo), snapshot, plan, validation, False,
            self.settings.limits, self.settings.timeout_seconds,
        )

        self.assertIn("staged top", run_git(self.repo, "diff", "--cached").stdout)
        self.assertNotIn("unstaged bottom", run_git(self.repo, "diff", "--cached").stdout)
        self.assertIn("unstaged bottom", run_git(self.repo, "diff").stdout)

    def test_workspace_drift_is_rejected_before_real_index_write(self) -> None:
        changed = list(self.base_lines)
        changed[1] = "planned top\n"
        write_file(self.repo, "code.txt", "".join(changed))
        snapshot = self.collect()
        plan = self.plan_for(snapshot, [[snapshot.expected_ids("hunk")[0]]])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")
        before_tree = run_git(self.repo, "write-tree").stdout.strip()
        changed[34] = "late edit\n"
        write_file(self.repo, "code.txt", "".join(changed))

        with self.assertRaisesRegex(PlanExecutionError, "工作区已变化"):
            self.executor.apply_next(
                str(self.repo), snapshot, plan, validation, False,
                self.settings.limits, self.settings.timeout_seconds,
            )

        self.assertEqual(run_git(self.repo, "write-tree").stdout.strip(), before_tree)

    def test_remaining_hunk_edit_after_commit_invalidates_remap(self) -> None:
        changed = list(self.base_lines)
        changed[1] = "planned top\n"
        changed[34] = "planned bottom\n"
        write_file(self.repo, "code.txt", "".join(changed))
        snapshot = self.collect()
        ids = list(snapshot.expected_ids("hunk"))
        plan = self.plan_for(snapshot, [[ids[0]], [ids[1]]])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")
        applied = self.executor.apply_next(
            str(self.repo), snapshot, plan, validation, False,
            self.settings.limits, self.settings.timeout_seconds,
        )
        ok, message = self.service.commit(applied.group.title)
        self.assertTrue(ok, message)
        changed[34] = "edited while awaiting commit\n"
        write_file(self.repo, "code.txt", "".join(changed))

        remapped = HunkPlanRemapper.advance(
            snapshot, self.collect(), plan, applied.group.group_id
        )

        self.assertFalse(remapped.advanced)
        self.assertIn("发生变化", remapped.message)

    def test_pure_rename_group_does_not_absorb_later_content_hunk(self) -> None:
        write_file(self.repo, "旧 名称.txt", "rename me\n")
        commit_all(self.repo, "chore: add rename fixture")
        run_git(self.repo, "mv", "旧 名称.txt", "新 名称.txt")
        write_file(self.repo, "新 名称.txt", "edited after rename\n")
        snapshot = self.collect()
        rename = next(change for change in snapshot.changes if change.staged)
        content = next(change for change in snapshot.changes if not change.staged)
        self.assertEqual(rename.hunks, ())
        plan = self.plan_for(snapshot, [
            [rename.change_id], [content.hunks[0].change_id],
        ])
        validation = CommitPlanValidator().validate(plan, snapshot, "hunk")

        self.executor.apply_next(
            str(self.repo), snapshot, plan, validation, False,
            self.settings.limits, self.settings.timeout_seconds,
        )

        cached = run_git(self.repo, "diff", "--cached").stdout
        self.assertIn("rename from", cached)
        self.assertNotIn("edited after rename", cached)
        self.assertIn("edited after rename", run_git(self.repo, "diff").stdout)

    def test_identical_hunk_is_remapped_after_sibling_commit(self) -> None:
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
        old_ids = list(snapshot.expected_ids("hunk"))
        self.assertEqual(len(set(old_ids)), 2)
        plan = self.plan_for(snapshot, [[old_ids[0]], [old_ids[1]]])

        fresh, remapped = self.apply_and_commit(snapshot, plan)

        self.assertTrue(remapped.advanced)
        new_id = fresh.expected_ids("hunk")[0]
        self.assertNotEqual(new_id, old_ids[1])
        self.assertEqual(remapped.plan.groups[0].change_ids, (new_id,))
        fresh, remapped = self.apply_and_commit(fresh, remapped.plan)
        self.assertTrue(remapped.completed)
        self.assertEqual(fresh.changes, ())


if __name__ == "__main__":
    unittest.main()
