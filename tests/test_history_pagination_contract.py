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
    assert 'function _requestTimelineMore()' in source
    assert 'function _ensureTimelineViewport()' in source
    assert 'root.timelineViewport = root._findTimelineViewportForProbe(root)' in source
    assert 'function _handleLogReady(repoPath, skip, batch)' in source
    assert 'property var timelinePendingLog: null' in source
    assert 'property bool timelineRefreshPending: false' in source
    assert 'readonly property int timelineQuietPeriod:' in source
    assert 'blocking: false' in source
    assert 'onWheel: function(event) { root._observeTimelineWheel() }' in source
    log_ready = source.split(
        'function _handleLogReady(repoPath, skip, batch)', 1
    )[1].split('function _findTimelineViewportForProbe', 1)[0]
    assert 'var deferUntilIdle = !root._timelineScrollIdle()' in log_ready
    assert 'root.refreshing || skip === 0' in log_ready
    assert 'root.timelinePendingLog = {' in log_ready
    request_more = source.split('function _requestTimelineMore()', 1)[1].split(
        'function _ensureTimelineViewport()', 1
    )[0]
    assert 'root.loadMore()' in request_more
    assert 'if (!root._timelineScrollIdle()) return' not in request_more
    assert 'root.timelinePendingLog = {' in source
    assert 'id: timelineLogAfterMotion' in source
    assert 'id: timelineRefreshAfterMotion' in source
    assert 'root.timelineViewport = null' not in source
    assert 'var bottom = originY + contentHeight' in source
    assert (
        'contentY + viewportHeight >= bottom - root.timelinePrefetchDistance'
        in source
    )
    assert 'onTriggered: root._probeTimelineEnd()' in source
    assert 'running: root.pageActive && root.initialized' in source
