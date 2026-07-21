# coding: utf-8
from __future__ import annotations

import unittest
from dataclasses import replace

from app.common.ai_commit_models import (
    ChangeSnapshot,
    CommitPlan,
    FileChangeSnapshot,
    HunkChange,
)
from app_qml.backend.ai_commit_plan_model import AiCommitPlanModel


class AiCommitPlanModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = ChangeSnapshot(
            "snapshot", "workspace", "repo", "head", "master", True, True,
            (
                FileChangeSnapshot(
                    "file_code", "src/a.py", "src/a.py", "src/a.py", "M",
                    False, False, False, "", 1, 1, "diff --git a/src/a.py b/src/a.py",
                ),
                FileChangeSnapshot(
                    "file_test", "tests/test_a.py", "", "tests/test_a.py", "A",
                    False, False, False, "", 2, 0, "diff --git a/tests/test_a.py b/tests/test_a.py",
                ),
            ),
        )
        self.plan = CommitPlan.from_mapping({
            "schema_version": "1",
            "snapshot_id": "snapshot",
            "level": "file",
            "summary": "实现并验证",
            "groups": [
                {
                    "group_id": "code",
                    "title": "feat: 实现功能",
                    "body": "",
                    "change_ids": ["file_code"],
                    "depends_on": [],
                    "rationale": "实现",
                    "warnings": [],
                },
                {
                    "group_id": "tests",
                    "title": "test: 补充测试",
                    "body": "",
                    "change_ids": ["file_test"],
                    "depends_on": ["code"],
                    "rationale": "验证",
                    "warnings": [],
                },
            ],
            "unassigned_change_ids": [],
            "warnings": [],
        })
        self.model = AiCommitPlanModel()
        self.model.load(self.plan, self.snapshot)

    def test_manual_move_revalidates_coverage_and_empty_group_removal(self) -> None:
        self.assertTrue(self.model.executable)
        self.assertTrue(self.model.moveChange("file_code", "tests"))
        self.assertFalse(self.model.valid)
        self.assertIn("empty_group", {item["code"] for item in self.model.issues})

        self.assertTrue(self.model.removeEmptyGroup("code"))
        self.assertTrue(self.model.valid)
        self.assertTrue(self.model.executable)
        self.assertEqual(
            [item["path"] for item in self.model.groups[0]["changes"]],
            ["tests/test_a.py", "src/a.py"],
        )

    def test_unassigned_change_blocks_execution_without_losing_coverage(self) -> None:
        self.assertTrue(self.model.moveChange("file_code", ""))
        self.assertFalse(self.model.valid)
        self.assertTrue(self.model.removeEmptyGroup("code"))
        self.assertTrue(self.model.valid)
        self.assertFalse(self.model.executable)
        self.assertEqual(self.model.unassignedChanges[0]["changeId"], "file_code")
        self.assertTrue(self.model.moveChange("file_code", "tests"))
        self.assertTrue(self.model.executable)

    def test_group_reorder_exposes_dependency_violation(self) -> None:
        self.assertTrue(self.model.moveGroup("tests", 0))
        self.assertFalse(self.model.valid)
        self.assertIn("dependency_order", {item["code"] for item in self.model.issues})
        self.assertTrue(self.model.moveGroup("tests", 1))
        self.assertTrue(self.model.valid)

    def test_add_edit_and_remove_manual_group(self) -> None:
        group_id = self.model.addGroup()
        self.assertEqual(group_id, "manual-1")
        self.assertFalse(self.model.valid)
        self.assertTrue(self.model.updateGroupMessage(group_id, "docs: 补充说明", "正文"))
        self.assertTrue(self.model.removeEmptyGroup(group_id))
        self.assertTrue(self.model.valid)

    def test_group_patch_comes_only_from_snapshot(self) -> None:
        patch = self.model.getGroupPatch("code")
        self.assertIn("# src/a.py", patch)
        self.assertIn("diff --git", patch)
        self.assertEqual(self.model.getGroupPatch("missing"), "")

    def test_stale_plan_is_visible_but_not_executable(self) -> None:
        self.model.markStale()
        self.assertTrue(self.model.hasPlan)
        self.assertTrue(self.model.stale)
        self.assertFalse(self.model.executable)
        self.assertIn("stale_plan", {item["code"] for item in self.model.issues})

    def test_advance_rejects_same_path_with_changed_patch(self) -> None:
        fresh_change = replace(
            self.snapshot.changes[1],
            change_id="fresh_test",
            patch="diff --git changed during commit",
        )
        fresh = replace(
            self.snapshot,
            snapshot_id="fresh",
            workspace_fingerprint="fresh-workspace",
            changes=(fresh_change,),
        )
        ok, completed, message = self.model.advance_after_commit("code", fresh)
        self.assertFalse(ok)
        self.assertFalse(completed)
        self.assertIn("发生变化", message)

    def test_final_group_requires_clean_remaining_workspace(self) -> None:
        self.assertTrue(self.model.moveChange("file_code", "tests"))
        self.assertTrue(self.model.removeEmptyGroup("code"))
        fresh = replace(
            self.snapshot,
            snapshot_id="fresh",
            changes=(replace(self.snapshot.changes[0], change_id="unexpected"),),
        )
        ok, completed, message = self.model.advance_after_commit("tests", fresh)
        self.assertFalse(ok)
        self.assertFalse(completed)
        self.assertIn("仍有新改动", message)

    def test_hunk_plan_exposes_context_coverage_and_manual_movement(self) -> None:
        hunks = (
            HunkChange(
                "hunk_top", "@@ -1 +1 @@", 1, 1, 1, 1, 1, 1,
                "@@ -1 +1 @@\n-old top\n+new top\n",
            ),
            HunkChange(
                "hunk_bottom", "@@ -20 +20 @@", 20, 1, 20, 1, 1, 1,
                "@@ -20 +20 @@\n-old bottom\n+new bottom\n",
            ),
        )
        snapshot = replace(
            self.snapshot,
            changes=(replace(
                self.snapshot.changes[0],
                patch=(
                    "diff --git a/src/a.py b/src/a.py\n"
                    "--- a/src/a.py\n"
                    "+++ b/src/a.py\n"
                    + "".join(hunk.content for hunk in hunks)
                ),
                hunks=hunks,
            ),),
        )
        plan = CommitPlan.from_mapping({
            "schema_version": "1",
            "snapshot_id": snapshot.snapshot_id,
            "level": "hunk",
            "summary": "按代码块拆分",
            "groups": [
                {
                    "group_id": "top",
                    "title": "feat: 修改顶部",
                    "body": "",
                    "change_ids": ["hunk_top"],
                    "depends_on": [],
                    "rationale": "顶部逻辑",
                    "warnings": [],
                },
                {
                    "group_id": "bottom",
                    "title": "test: 修改底部",
                    "body": "",
                    "change_ids": ["hunk_bottom"],
                    "depends_on": [],
                    "rationale": "底部逻辑",
                    "warnings": [],
                },
            ],
            "unassigned_change_ids": [],
            "warnings": [],
        })

        self.model.load(plan, snapshot)

        self.assertEqual(self.model.level, "hunk")
        self.assertEqual(self.model.coverage, {
            "total": 2, "assigned": 2, "unassigned": 0,
            "duplicates": 0, "percent": 100,
        })
        first_change = self.model.groups[0]["changes"][0]
        self.assertEqual(first_change["kind"], "hunk")
        self.assertIn("new top", first_change["content"])
        self.assertFalse(first_change["content"].startswith("@@"))
        self.assertIn("@@ -1", first_change["header"])
        preview = self.model.getGroupPatch("top")
        self.assertIn("diff --git a/src/a.py b/src/a.py", preview)
        self.assertIn("new top", preview)
        self.assertNotIn("new bottom", preview)
        self.assertTrue(self.model.moveChange("hunk_bottom", ""))
        self.assertEqual(self.model.coverage["assigned"], 1)
        self.assertEqual(self.model.coverage["unassigned"], 1)
        self.assertFalse(self.model.executable)


if __name__ == "__main__":
    unittest.main()
