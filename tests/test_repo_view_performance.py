from pathlib import Path
import unittest


class RepoViewPerformanceTest(unittest.TestCase):
    def test_change_list_uses_backend_model_and_reuses_delegates(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("GitBridge.fileChangeModel", source)
        self.assertIn("reuseItems: true", source)
        self.assertNotIn("ListModel { id: changeModel }", source)
        self.assertNotIn("changeModel.append", source)

    def test_advanced_view_loads_repository_state_in_background(self) -> None:
        source = Path("app_qml/qml/views/AdvancedView.qml").read_text(encoding="utf-8")

        self.assertIn("GitBridge.requestAdvancedState()", source)
        self.assertIn("function onAdvancedStateReady", source)
        self.assertIn("interval: GitBridge.pollIntervalMs", source)
        self.assertIn("running: root.visible && !!GitBridge && !!GitBridge.repoPath", source)
        self.assertIn("if (!root._advancedRequesting) root.reload()", source)
        self.assertIn("onVisibleChanged", source)
        self.assertNotIn("GitBridge.getWorktrees()", source)
        self.assertNotIn("GitBridge.getSubmodules()", source)


if __name__ == "__main__":
    unittest.main()
