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
        self.assertIn(
            "listCacheBuffer: changeScrollArea.itemHeight * 6",
            source,
        )
        self.assertNotIn("listCacheBuffer: 0", source)
        self.assertNotIn("ListModel { id: changeModel }", source)
        self.assertNotIn("changeModel.append", source)

    def test_change_list_only_instantiates_row_actions_on_hover(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("id: changeActionsLoader", source)
        self.assertIn("active: hover.hovered", source)
        self.assertIn("onRowPathChanged:", source)
        self.assertIn("onRowStagedChanged:", source)
        self.assertIn("sourceComponent: Component {", source)
        self.assertNotIn("visible: hover.hovered", source)

    def test_change_list_actions_overlay_text_without_joining_row_layout(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("id: changeRowContent", source)
        self.assertIn("z: 0", source)
        self.assertNotIn("id: changeActionsSlot", source)
        self.assertIn(
            "readonly property int actionCount: model.staged ? 2 : 3",
            source,
        )
        self.assertIn("anchors.right: parent.right", source)
        self.assertIn("anchors.verticalCenter: parent.verticalCenter", source)
        self.assertIn("z: 1", source)
        self.assertIn("id: changeActions", source)
        overlay_start = source.index("id: changeActions")
        overlay_end = source.index("RowLayout {", overlay_start)
        overlay_source = source[overlay_start:overlay_end]
        self.assertIn("color: Qt.tint(", overlay_source)
        self.assertIn("Fluent.Enums.cardColor", overlay_source)
        self.assertIn("Fluent.Enums.stateColor.hover", overlay_source)
        self.assertNotIn(
            "color: Fluent.Enums.stateColor.hover",
            overlay_source,
        )
        self.assertIn("spacing: Fluent.Enums.spacing.xxs", source)
        self.assertEqual(
            source.count("preferredWidth: Fluent.Enums.controlSize.inputHeight"),
            3,
        )
        self.assertIn('text: changeActions.rowStaged ? "取消" : "暂存"', source)
        self.assertIn('text: "丢弃"', source)
        self.assertIn('text: "历史"', source)
        self.assertNotIn("Fluent.MenuCore {", source)

    def test_repository_split_keeps_diff_oriented_ratio(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("splitPosition: 0.35", source)
        self.assertNotIn("splitPosition: 0.42", source)

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
        menu_source = Path(
            "app_qml/qml/components/RepositorySearchMenu.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("repoPathFontMetrics.elidedText(", source)
        self.assertIn("Text.ElideMiddle", source)
        self.assertIn("pathFormatter: root._displayRepoPath", source)
        self.assertIn(
            "repositorySearchMenu.prepareForOpen(pathList)",
            source,
        )
        self.assertIn("feature: Fluent.Enums.button.feature_split", source)
        self.assertIn("menu: repositorySearchMenu", source)
        self.assertIn("GitBridge.getRecentRepos()", source)
        self.assertIn("RepoScanner.mergeWithOpenedRepos(recent)", source)
        self.assertNotIn("var all = recent.concat(scanned)", source)
        self.assertNotIn("repositoryOpenButtonGroup", source)
        self.assertNotIn("repositoryOpenMenuButton", source)
        self.assertIn("GitBridge.openRepoAsync(path)", source)
        self.assertIn("if (repositorySearchMenu.isOpen)", source)
        self.assertIn("repositorySearchMenu.setPaths(openButton.pathList)", source)
        self.assertIn("pathSelected(selectedPath)", menu_source)
        self.assertNotIn("GitBridge.openRepoAsync(pathList[index])", source)

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
