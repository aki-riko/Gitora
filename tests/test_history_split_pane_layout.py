import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY_VIEW = ROOT / "app_qml" / "qml" / "views" / "HistoryView.qml"


class HistorySplitPaneLayoutTest(unittest.TestCase):
    def test_split_position_is_clamped_to_readable_pane_widths(self):
        source = HISTORY_VIEW.read_text(encoding="utf-8")

        self.assertIn("id: historySplitPane", source)
        self.assertIn("minimumFirstPaneWidth: historyHeader.implicitWidth", source)
        self.assertIn("minimumSecondPaneWidth: 360", source)
        self.assertIn("onSplitPositionChanged: clampSplitPosition()", source)
        self.assertIn("onWidthChanged: clampSplitPosition()", source)
        self.assertIn("onMinimumFirstPaneWidthChanged: clampSplitPosition()", source)


if __name__ == "__main__":
    unittest.main()
