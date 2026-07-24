# coding: utf-8
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CherryPickTargetContractTest(unittest.TestCase):
    def test_history_cherry_pick_requires_explicit_local_target_branch(self) -> None:
        source = (ROOT / "app_qml" / "qml" / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("function _openCherryPickDialog()", source)
        self.assertIn("GitBridge.requestBranches()", source)
        self.assertIn('objectName: "cherryPickTargetCombo"', source)
        self.assertIn("text: \"目标分支\"", source)
        self.assertIn("GitBridge.cherryPickToBranch(commit.hash, target)", source)
        self.assertIn("!branch.isRemote", source)
        self.assertIn("root.cherryPickCurrentBranch", source)

    def test_bridge_exposes_target_branch_cherry_pick(self) -> None:
        source = (ROOT / "app_qml" / "backend" / "git_bridge.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("def cherryPickToBranch", source)
        self.assertIn("self._svc.cherry_pick_to_branch", source)


if __name__ == "__main__":
    unittest.main()
