# coding: utf-8
"""历史页触底分页合同。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY_VIEW = ROOT / "app_qml" / "qml" / "views" / "HistoryView.qml"


def test_history_pagination_probes_virtual_viewport_origin_and_bottom() -> None:
    source = HISTORY_VIEW.read_text(encoding="utf-8")

    assert 'id: historyTimeline' in source
    assert 'property var timelineViewport: null' in source
    assert 'readonly property real timelinePrefetchDistance: 600' in source
    assert 'function _findTimelineViewportForProbe(item)' in source
    assert 'function _probeTimelineEnd()' in source
    assert 'var bottom = originY + contentHeight' in source
    assert (
        'contentY + viewportHeight >= bottom - root.timelinePrefetchDistance'
        in source
    )
    assert 'onTriggered: root._probeTimelineEnd()' in source
    assert 'running: root.pageActive && root.initialized' in source
