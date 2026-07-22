from pathlib import Path
import unittest


class RepoViewPerformanceTest(unittest.TestCase):
    def test_quick_commit_message_is_only_cleared_after_matching_success(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("property bool _quickCommitPushPending: false", source)
        self.assertIn("function onQuickCommitPushFinished(ok, msg)", source)
        self.assertIn("if (ok && GitBridge && GitBridge.repoPath === submittedRepoPath", source)
        self.assertIn("root._commitMessage() === submittedMessage", source)
        self.assertNotIn(
            'GitBridge.quickCommitPush(root._commitMessage())\n                    root._clearCommitMessage()',
            source,
        )

    def test_change_list_uses_backend_model_and_reuses_delegates(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("GitBridge.fileChangeModel", source)
        self.assertIn("reuseItems: true", source)
        self.assertNotIn("ListModel { id: changeModel }", source)
        self.assertNotIn("changeModel.append", source)

    def test_change_list_actions_use_compact_button_group(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("id: changeActions", source)
        self.assertIn("spacing: Fluent.Enums.spacing.xxs", source)
        self.assertEqual(
            source.count("preferredWidth: Fluent.Enums.controlSize.inputHeight"),
            3,
        )

    def test_change_summary_actions_live_inside_card_above_separator(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        card_index = source.index("id: changeCard")
        header_index = source.index("id: changeCardHeader")
        separator_index = source.index("id: changeCardHeaderSeparator")
        body_index = source.index("id: changeCardBody")

        self.assertLess(card_index, header_index)
        self.assertLess(header_index, separator_index)
        self.assertLess(separator_index, body_index)

    def test_repository_dropdown_limits_display_width_but_opens_original_path(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("repoPathFontMetrics.elidedText(", source)
        self.assertIn("Text.ElideMiddle", source)
        self.assertIn('"text": root._displayRepoPath(pathList[i])', source)
        self.assertIn("GitBridge.openRepoAsync(pathList[index])", source)
        self.assertNotIn('"text": pathList[i]', source)

    def test_advanced_view_loads_repository_state_in_background(self) -> None:
        source = Path("app_qml/qml/views/AdvancedView.qml").read_text(encoding="utf-8")

        self.assertIn("GitBridge.requestAdvancedState()", source)
        self.assertIn("function onAdvancedStateReady", source)
        self.assertIn("interval: GitBridge.pollIntervalMs", source)
        self.assertIn("running: root.visible && !!GitBridge && !!GitBridge.repoPath", source)
        self.assertIn("if (!root._advancedRequesting) root.reload()", source)
        self.assertIn("onVisibleChanged", source)
        self.assertNotIn("正在后台读取高级仓库信息", source)
        self.assertNotIn("GitBridge.getWorktrees()", source)
        self.assertNotIn("GitBridge.getSubmodules()", source)


if __name__ == "__main__":
    unittest.main()
