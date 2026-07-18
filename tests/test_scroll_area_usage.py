# coding: utf-8
import re
import unittest
from pathlib import Path


QML_ROOT = Path(__file__).resolve().parents[1] / "app_qml" / "qml"
RAW_SCROLL_DECLARATION = re.compile(r"^\s*(?:ListView|Flickable)\s*\{", re.MULTILINE)


class ScrollAreaUsageTest(unittest.TestCase):
    def test_business_qml_uses_prism_scroll_area(self) -> None:
        violations = []
        for qml_path in sorted(QML_ROOT.rglob("*.qml")):
            source = qml_path.read_text(encoding="utf-8")
            if RAW_SCROLL_DECLARATION.search(source):
                violations.append(str(qml_path.relative_to(QML_ROOT)))

        self.assertEqual([], violations, f"发现绕过 ScrollArea 的滚动容器: {violations}")

    def test_virtualized_lists_use_list_mode(self) -> None:
        expected_counts = {
            "views/TagView.qml": 1,
            "views/RepoView.qml": 2,
            "components/CleanDialog.qml": 1,
            "components/ConflictViewerDialog.qml": 1,
            "components/ReflogDialog.qml": 1,
            "components/FileHistoryDialog.qml": 1,
        }
        marker = "type: Fluent.Enums.scroll.type_list"
        for relative_path, expected_count in expected_counts.items():
            source = (QML_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertEqual(expected_count, source.count(marker), relative_path)

    def test_text_viewers_keep_two_axis_scrolling(self) -> None:
        for relative_path in (
            "components/DiffViewer.qml",
            "components/FileHistoryDialog.qml",
        ):
            source = (QML_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("orientation: Qt.Horizontal | Qt.Vertical", source, relative_path)


if __name__ == "__main__":
    unittest.main()
