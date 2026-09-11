# coding: utf-8
import unittest
from pathlib import Path


QML_ROOT = Path(__file__).resolve().parents[1] / "app_qml" / "qml"
PROJECT_ROOT = QML_ROOT.parents[1]


class HistoryDiffRefreshContractTest(unittest.TestCase):
    def test_commit_detail_uses_most_of_the_window_and_gives_diff_remaining_space(self) -> None:
        source = (QML_ROOT / "components" / "CommitDetailDialog.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("readonly property real viewportRatio: 0.92", source)
        self.assertIn("contentWidth: dlg._targetDialogWidth", source)
        self.assertIn("height: dlg._targetContentHeight", source)
        self.assertIn("id: headerLayout", source)
        # 文件列表为左侧窄栏(多文件提交才显示),diff 吃满剩余宽高
        self.assertIn("visible: dlg.fileRows.length > 1", source)
        self.assertIn("Layout.preferredWidth: 200", source)
        self.assertIn("Layout.fillHeight: true", source)
        self.assertNotIn("width: 580", source)
        self.assertNotIn("Layout.preferredHeight: 260", source)

    def test_history_status_refresh_keeps_existing_timeline_until_data_arrives(self) -> None:
        source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )
        status_handler = source.split("function onStatusChanged()", 1)[1].split(
            "function onRepoPathChanged", 1
        )[0]
        operation_handler = source.split("function _op(", 1)[1].split(
            "function _askReset", 1
        )[0]

        self.assertIn("root.refreshIncrementally()", status_handler)
        self.assertIn("task.succeeded.connect", operation_handler)
        self.assertIn("root.refreshIncrementally()", operation_handler)
        self.assertNotIn("root.resetAndLoad()", status_handler)
        self.assertNotIn("root.resetAndLoad()", operation_handler)

        self.assertIn("property bool refreshing: false", source)
        self.assertIn("readonly property int maxHistoryCommits: 2000", source)
        self.assertIn("root.refreshCount = Math.min(", source)
        self.assertIn("property bool refreshPending: false", source)
        self.assertIn("function finishLoading()", source)
        self.assertIn("root.refreshPending = true", source)
        self.assertIn("if (root.refreshing)", source)
        self.assertIn("root.allCommits = batch", source)
        self.assertIn("root._restoreSelection(batch)", source)
        self.assertIn("function _sameTimelineCommits(left, right)", source)
        self.assertIn("if (historyChanged) root.allCommits = batch", source)
        self.assertIn("if (historyChanged) root._restoreSelection(batch)", source)
        self.assertIn("function _syncRenderedTimelineItems()", source)
        self.assertNotIn("root.renderedTimelineItems = []", source)
        self.assertIn("root.renderedTimelineItems = nextItems", source)
        self.assertIn("items: root.renderedTimelineItems", source)

    def test_history_scope_switch_controls_log_search_and_visible_context(self) -> None:
        source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("property bool includeAllRefs: false", source)
        self.assertIn('property string currentBranch: ""', source)
        self.assertIn("property int totalCommitCount: -1", source)
        self.assertIn('objectName: "historyScopeCombo"', source)
        self.assertIn(
            '"当前分支",\n                            "全部分支"', source
        )
        self.assertNotIn(
            '"当前分支 · " + (root.currentBranch || "正在读取…")', source
        )
        self.assertIn("function setHistoryScope(scopeIndex)", source)
        self.assertIn("function requestCurrentBranch()", source)
        self.assertIn("GitBridge.requestCurrentBranch()", source)
        self.assertIn("GitBridge.requestHistoryCount(root.includeAllRefs)", source)
        self.assertIn(
            "function onHistoryCountReady(repoPath, count, includeAllRefs)",
            source,
        )
        self.assertIn("readonly property bool pageActive:", source)
        self.assertIn("!root.parent || root.parent.visible", source)
        self.assertIn("onPageActiveChanged:", source)
        self.assertIn("if (root.pageActive) root.refreshIncrementally()", source)
        self.assertIn(
            "root.loadedCount, root.includeAllRefs", source
        )
        self.assertIn(
            'searchInput.text, "all", root.includeAllRefs', source
        )
        self.assertIn(
            "requestLog(root.refreshCount, 0, root.includeAllRefs)", source
        )
        self.assertIn(
            'requestSearch(query, "all", root.includeAllRefs)', source
        )
        self.assertIn('? " · 全部分支"', source)
        self.assertIn('root.currentBranch || "正在读取…"', source)
        self.assertIn('root.totalCommitCount + " 条提交"', source)
        self.assertIn("onOperationSucceeded: root.refreshIncrementally()", source)

    def test_history_search_uses_progressive_results_and_cancellation(self) -> None:
        source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("property bool searchDeepening: false", source)
        self.assertIn("GitBridge.cancelSearch()", source)
        self.assertIn("function onSearchPreviewReady(repoPath, results)", source)
        self.assertIn("root.searchDeepening = true", source)
        self.assertIn('root.searchDeepening ? " · 后台补全中" : ""', source)

    def test_history_timeline_uses_fluent_layered_surface(self) -> None:
        source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn('objectName: "historyTimelineSurface"', source)
        self.assertIn('objectName: "historyTimeline"', source)
        self.assertIn("color: Fluent.Enums.surfaceColor", source)
        self.assertIn("radius: Fluent.Enums.radius.large", source)
        self.assertIn("border.width: Fluent.Enums.border.thin", source)
        self.assertIn("anchors.margins: Fluent.Enums.spacing.m", source)

    def test_history_detail_fills_space_with_real_commit_files(self) -> None:
        history_source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )
        source = (QML_ROOT / "components" / "CommitFilesPanel.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("CommitFilesPanel {", history_source)
        self.assertIn("commit: root.selectedCommit", history_source)
        self.assertIn('objectName: "historyCommitFilesPanel"', source)
        self.assertIn('objectName: "historyCommitFilesList"', source)
        self.assertIn("GitBridge.requestCommitFiles(hash)", source)
        self.assertIn('text: "变更文件"', source)
        self.assertIn('text: "新增 " + root.countStatus("A")', source)
        self.assertIn('text: "修改 " + root.countStatus("M")', source)
        self.assertIn('text: "删除 " + root.countStatus("D")', source)
        self.assertIn("root.displayPath(modelData.path)", source)
        self.assertIn("property var fileRows: []", source)
        self.assertIn("root.fileRows = files || []", source)
        self.assertIn("type: Fluent.Enums.scroll.type_list", source)
        self.assertIn("selectable: false", source)
        self.assertIn("reuseItems: true", source)
        self.assertIn("model: root.fileRows", source)
        self.assertIn("function onCommitFilesReady(repoPath, hash, files, total, isTruncated, counts)", source)
        self.assertNotIn("commitFilesModel.append", source)
        self.assertNotIn(
            "Item { Layout.fillHeight: true }\n\n                    Fluent.Separator",
            history_source,
        )

    def test_history_commit_actions_use_chinese_labels_and_english_tooltips(self) -> None:
        source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )
        action_area = source.split("// ── 操作区 ──", 1)[1].split(
            "// 危险操作:reset 二次确认", 1
        )[0]

        for chinese_label, english_tooltip in (
            ("检出提交", "Checkout"),
            ("拣选提交", "Cherry-pick"),
            ("撤销提交", "Revert"),
            ("重置", "Reset"),
        ):
            self.assertIn(f'text: "{chinese_label}"', action_area)
            self.assertIn(f'toolTipText: "{english_tooltip}"', action_area)
            self.assertNotIn(f'text: "{english_tooltip}"', action_area)

    def test_history_commit_files_ignore_stale_async_results(self) -> None:
        source = (QML_ROOT / "components" / "CommitFilesPanel.qml").read_text(
            encoding="utf-8"
        )
        handler = source.split("function onCommitFilesReady", 1)[1].split(
            "\n        }", 1
        )[0]

        self.assertIn("repoPath !== GitBridge.repoPath", handler)
        self.assertIn("repoPath !== root.requestRepoPath", handler)
        self.assertIn("hash !== root.requestHash", handler)
        self.assertIn("root.commit.hash !== hash", handler)

    def test_diff_viewer_renders_virtualized_rows_without_html_table(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        # 旧的大 HTML 表格渲染必须彻底移除
        self.assertNotIn("<td", source)
        self.assertNotIn("TextEdit", source)
        self.assertNotIn("disableTextViewportCulling", source)
        # 虚拟化窗口化渲染必须存在:delegate 池 + 可见窗口同步
        self.assertIn("function _syncWindow", source)
        self.assertIn("rowDelegateComponent.createObject(canvas)", source)
        self.assertIn("DiffRowDelegate", source)

    def test_diff_viewer_collapses_noise_meta_and_fits_viewport_width(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        # index/---/+++ 等纯噪音行在视图层折叠;文件头行保留为文件带
        self.assertIn("function _collapseFileMeta", source)
        self.assertIn('x.indexOf("index ") === 0', source)
        self.assertIn('x.indexOf("+++ ") === 0', source)
        self.assertIn("function _fileDisplayText", source)
        # 横向内容宽必须与 Flickable 视口宽比较,禁止用外层宽造成常驻假横向滚动条
        self.assertIn("readonly property real _viewportWidth", source)
        self.assertIn("Math.max(root._viewportWidth, root._contentWidth)", source)
        self.assertNotIn("Math.max(diffScrollArea.width", source)

    def test_diff_viewer_is_unified_only_without_split_mode(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        # 分栏模式已整体移除:无 displayMode 属性、无配对构建、无模式切换按钮
        self.assertNotIn("displayMode", source)
        self.assertNotIn("_buildSplitRows", source)
        self.assertNotIn('"split"', source)
        self.assertNotIn('text: "分栏"', source)
        self.assertNotIn('text: "统一"', source)

    def test_diff_line_number_columns_have_fixed_width(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "readonly property real lineNoWidth: _maxDigits * charWidth",
            source,
        )
        self.assertIn("property int _maxDigits: 3", source)

    def test_diff_viewer_uses_async_row_model_with_stale_guard(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("GitBridge.requestDiffRows(root.rawDiff)", source)
        self.assertIn("function onDiffRowsReady(rawDiff, rowsJson)", source)
        self.assertIn("rawDiff !== root.rawDiff", source)
        # 双轴滚动契约保持(引擎 ScrollArea 默认模式)
        self.assertIn("orientation: Qt.Horizontal | Qt.Vertical", source)

    def test_commit_detail_explicitly_finishes_repeated_diff_loading(self) -> None:
        viewer_source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )
        dialog_source = (
            QML_ROOT / "components" / "CommitDetailDialog.qml"
        ).read_text(encoding="utf-8")

        set_diff = viewer_source.split("function setDiff", 1)[1].split("\n    }", 1)[0]
        diff_ready = dialog_source.split("function onCommitDiffReady", 1)[1].split(
            "\n        }", 1
        )[0]

        self.assertIn("root.loading = false", set_diff)
        self.assertIn("root._reloadFileModel()", set_diff)
        self.assertIn("root._requestRows()", set_diff)
        self.assertIn(
            "commitDiffViewer.setDiff(dlg._rawDiff, dlg._selectedFilePath)",
            diff_ready,
        )

    def test_commit_detail_loads_diff_only_for_selected_file(self) -> None:
        source = (QML_ROOT / "components" / "CommitDetailDialog.qml").read_text(
            encoding="utf-8"
        )
        open_for = source.split("function openFor", 1)[1].split(
            "\n    }", 1
        )[0]

        self.assertIn("GitBridge.requestCommitFiles(hash)", open_for)
        self.assertIn("GitBridge.requestCommitDiff(hash)", open_for)
        self.assertIn("GitBridge.requestCommitFileDiff(", source)
        self.assertIn("function onCommitFileDiffReady", source)
        self.assertIn("path !== dlg._selectedFilePath", source)

    def test_timeline_trace_is_opt_in_and_covers_refresh_and_scroll_edges(self) -> None:
        history_source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )
        main_source = (PROJECT_ROOT / "app_qml" / "main_qml.py").read_text(
            encoding="utf-8"
        )
        bridge_source = (
            PROJECT_ROOT / "app_qml" / "backend" / "git_bridge.py"
        ).read_text(encoding="utf-8")

        self.assertIn('"GITORA_TIMELINE_TRACE"', main_source)
        self.assertIn('"GitoraTimelineTraceEnabled"', main_source)
        self.assertIn("readonly property bool timelineTraceEnabled", history_source)
        self.assertIn('"[TIMELINE_TRACE]', history_source)
        self.assertIn('"viewport.contentY"', history_source)
        self.assertIn('"helper.smoothPos"', history_source)
        self.assertIn('"refresh.request_log"', history_source)
        self.assertIn('"log.apply.refresh_decision"', history_source)
        self.assertIn('"statusChanged.emit"', bridge_source)
        self.assertIn('"log.request"', bridge_source)
        self.assertIn('"log.result_emit"', bridge_source)


if __name__ == "__main__":
    unittest.main()
