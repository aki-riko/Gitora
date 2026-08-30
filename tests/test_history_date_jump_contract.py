import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = ROOT / "app_qml" / "qml"


class HistoryDateJumpContractTest(unittest.TestCase):
    def test_history_exposes_calendar_picker_and_date_group_jump(self) -> None:
        history_source = (QML_ROOT / "views" / "HistoryView.qml").read_text(
            encoding="utf-8"
        )
        model_source = (QML_ROOT / "components" / "CommitTimelineModel.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn('property string pendingJumpDate: ""', history_source)
        self.assertIn('objectName: "historyDatePicker"', history_source)
        self.assertIn('placeholderText: "跳转日期"', history_source)
        self.assertIn("onDateChanged: function(year, month, day)", history_source)
        self.assertIn("root.jumpToDate(year, month, day)", history_source)
        self.assertIn("function jumpToDate(year, month, day)", history_source)
        self.assertIn("function _findDateJumpViewport(item)", history_source)
        self.assertIn(
            'item.objectName === "timelineVirtualViewport"', history_source
        )
        self.assertIn(
            "viewport.positionViewAtIndex(rowIndex, ListView.Beginning)",
            history_source,
        )
        self.assertIn("root._schedulePendingDateJump()", history_source)
        self.assertIn('"dateKey": _dateKey(commit.date)', model_source)
        self.assertIn("function _timeText(dateStr)", model_source)
        self.assertIn("function _timePeriod(dateStr)", model_source)
        self.assertIn('"time": _timeText(commit.date)', model_source)
        self.assertIn('"timePeriod": _timePeriod(commit.date)', model_source)

if __name__ == "__main__":
    unittest.main()
