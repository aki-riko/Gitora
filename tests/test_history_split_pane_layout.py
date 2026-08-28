import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY_VIEW = ROOT / "app_qml" / "qml" / "views" / "HistoryView.qml"


class HistorySplitPaneLayoutTest(unittest.TestCase):
    def test_split_pane_owns_readable_width_clamping(self):
        source = HISTORY_VIEW.read_text(encoding="utf-8")

        self.assertIn("id: historySplitPane", source)
        self.assertIn('objectName: "historySplitPane"', source)
        self.assertIn("minimumFirstPaneWidth: 520", source)
        self.assertIn("minimumSecondPaneWidth: 360", source)
        self.assertIn("firstMinimumSize: minimumFirstPaneWidth", source)
        self.assertIn("secondMinimumSize: minimumSecondPaneWidth", source)
        self.assertIn("Flow {", source)
        self.assertIn('objectName: "historyHeader"', source)
        self.assertNotIn("function clampSplitPosition()", source)
        self.assertNotIn("onSplitPositionChanged: clampSplitPosition()", source)


if __name__ == "__main__":
    unittest.main()
