# coding: utf-8
import unittest
from pathlib import Path


QML_ROOT = Path(__file__).resolve().parents[1] / "app_qml" / "qml"


class HistoryDiffRefreshContractTest(unittest.TestCase):
    def test_commit_detail_uses_most_of_the_window_and_gives_diff_remaining_space(self) -> None:
        source = (QML_ROOT / "components" / "CommitDetailDialog.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn("readonly property real viewportRatio: 0.92", source)
        self.assertIn("contentWidth: dlg._targetDialogWidth", source)
        self.assertIn("height: dlg._targetContentHeight", source)
        self.assertIn("id: headerLayout", source)
        self.assertGreaterEqual(source.count("Layout.fillHeight: false"), 3)
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
        operation_handler = source.split("function _op(res)", 1)[1].split(
            "function _askReset", 1
        )[0]

        self.assertIn("root.refreshIncrementally()", status_handler)
        self.assertNotIn("root.resetAndLoad()", status_handler)
        self.assertNotIn("root.resetAndLoad()", operation_handler)

        self.assertIn("property bool refreshing: false", source)
        self.assertIn("root.refreshCount = Math.max(root.pageSize, root.loadedCount)", source)
        self.assertIn("if (root.refreshing)", source)
        self.assertIn("root.allCommits = batch", source)
        self.assertIn("root._restoreSelection(batch)", source)

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
        self.assertIn("root.displayPath(model.path)", source)
        self.assertNotIn(
            "Item { Layout.fillHeight: true }\n\n                    Fluent.Separator",
            history_source,
        )

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

    def test_diff_tables_do_not_use_full_span_rows_that_distort_columns(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("colspan=", source)
        self.assertIn('<td width="1"', source)
        self.assertIn("function _unifiedMetaRow", source)
        self.assertIn("function _splitMetaRow", source)

    def test_split_metadata_does_not_stretch_the_code_columns(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        split_meta = source.split("function _splitMetaRow", 1)[1].split("\n    }", 1)[0]
        self.assertIn("</table><div", split_meta)
        self.assertIn("root._escape(text)", split_meta)
        self.assertIn("root._tableStart()", split_meta)
        self.assertNotIn("root._textCell(text", split_meta)

    def test_diff_line_number_columns_have_no_horizontal_padding(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "readonly property int lineNumberHorizontalPadding: Fluent.Enums.spacing.none",
            source,
        )
        self.assertIn(
            "readonly property int contentHorizontalPadding: Fluent.Enums.spacing.xs",
            source,
        )
        num_cell = source.split("function _numCell", 1)[1].split("\n    }", 1)[0]
        self.assertIn("+ root.lineNumberHorizontalPadding +", num_cell)
        self.assertNotIn("root.contentHorizontalPadding", num_cell)
        self.assertEqual(source.count("+ root.contentHorizontalPadding +"), 2)
        self.assertNotIn("padding:0 8px", source)

    def test_rich_text_diff_disables_broken_viewport_culling_after_assignment(self) -> None:
        source = (QML_ROOT / "components" / "DiffViewer.qml").read_text(
            encoding="utf-8"
        )
        set_html = source.split("function _setHtml", 1)[1].split("\n    }", 1)[0]

        self.assertIn('diffArea.text = html || ""', set_html)
        self.assertIn(
            "QmlRenderBridge.disableTextViewportCulling(diffArea)", set_html
        )
        self.assertEqual(source.count("diffArea.text ="), 1)
        self.assertNotIn("smoothScroll: false", source)


if __name__ == "__main__":
    unittest.main()
