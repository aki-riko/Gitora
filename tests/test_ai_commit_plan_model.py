# coding: utf-8
from __future__ import annotations

import unittest

from app.common.ai_commit_models import (
    ChangeSnapshot,
    CommitPlan,
    FileChangeSnapshot,
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


if __name__ == "__main__":
    unittest.main()
