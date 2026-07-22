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

    def test_history_operations_rely_on_status_signal_for_single_reload(self) -> None:
        source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )
        status_handler = source.split("function onStatusChanged()", 1)[1].split(
            "function onRepoPathChanged", 1
        )[0]
        operation_handler = source.split("function _op(res)", 1)[1].split(
            "function _askReset", 1
        )[0]

        self.assertIn("root.resetAndLoad()", status_handler)
        self.assertNotIn("root.resetAndLoad()", operation_handler)

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


if __name__ == "__main__":
    unittest.main()
