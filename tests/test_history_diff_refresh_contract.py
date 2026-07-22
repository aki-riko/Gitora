# coding: utf-8
import unittest
from pathlib import Path


QML_ROOT = Path(__file__).resolve().parents[1] / "app_qml" / "qml"


class HistoryDiffRefreshContractTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
