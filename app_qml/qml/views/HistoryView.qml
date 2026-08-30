// 历史视图(阶段 2:迁移 history_interface.py)
// 布局:SplitPane(左:搜索+提交列表(分页无限滚动) / 右:提交详情+操作)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent
import "../components"

Item {
    id: root

    readonly property int pageSize: 30
    readonly property int maxHistoryCommits: 2000
    property int loadedCount: 0
    property bool hasMore: true
    property bool loading: false
    property bool searchDeepening: false
    property bool refreshing: false
    property bool refreshPending: false
    property bool timelineRefreshPending: false
    property var timelinePendingLog: null
    property int refreshCount: 0
    property bool searchMode: false
    property bool includeAllRefs: false
    property string currentBranch: ""
    property bool initialized: false
    readonly property bool pageActive: root.visible
        && (!root.parent || root.parent.visible)
    property var selectedCommit: null
    property string pendingJumpHash: ""
    property string pendingJumpDate: ""
    property var cherryPickBranches: []
    property string cherryPickCurrentBranch: ""
    property string cherryPickTargetBranch: ""
    property string cherryPickRequestRepoPath: ""

    property var allCommits: []        // 已加载的提交(累积)
    readonly property var timelineItems: historyTimelineModel.items
    readonly property int graphLaneCount: historyTimelineModel.laneCount
    property var renderedTimelineItems: []
    property int renderedTimelineCommitCount: 0
    property string renderedTimelineTopHash: ""
    property var timelineViewport: null
    property real timelineLastContentY: 0
    property bool timelineMotionObserved: false
    property double timelineLastMotionAt: 0
    property double timelineLastWheelAt: 0
    readonly property int timelineQuietPeriod: Fluent.Enums.duration.bounce
    readonly property real timelinePrefetchDistance: 600
    readonly property bool timelineTraceEnabled:
        typeof GitoraTimelineTraceEnabled !== "undefined"
            && GitoraTimelineTraceEnabled === true
    property int timelineTraceSequence: 0
    property double timelineTraceLastContentLogAt: 0
    property real timelineTraceLastLoggedContentY: 0
    property real timelineTraceLastDelta: 0
    property bool timelineTraceHasContentSample: false
    property double timelineTraceLastSmoothLogAt: 0
    property real timelineTraceLastLoggedSmoothPos: 0
    property real timelineTraceLastSmoothDelta: 0
    property bool timelineTraceHasSmoothSample: false
    property var timelineScrollHelper: null

    // Opt-in trace helper. It does no work while the flag is off.
    function _timelineTrace(eventName, details) {
        if (!root.timelineTraceEnabled) return
        root.timelineTraceSequence += 1
        var suffix = details ? " " + details : ""
        console.debug(
            "[TIMELINE_TRACE] side=qml #" + root.timelineTraceSequence
                + " t=" + Date.now() + " " + eventName + suffix
        )
    }

    function _findTimelineScrollHelper(item) {
        if (!item) return null
        var children = item.children || []
        for (var index = 0; index < children.length; index++) {
            var child = children[index]
            if (child && child.target === root.timelineViewport
                    && typeof child.scrollBy === "function")
                return child
            var found = root._findTimelineScrollHelper(child)
            if (found) return found
        }
        return null
    }

    function _ensureTimelineTraceObjects() {
        if (!root.timelineTraceEnabled || !root.timelineViewport) return
        if (!root.timelineScrollHelper)
            root.timelineScrollHelper = root._findTimelineScrollHelper(
                root.timelineViewport
            )
    }

    // ==================== 数据加载 ====================
    function resetAndLoad() {
        if (GitBridge) GitBridge.cancelSearch()
        requestCurrentBranch()
        root.allCommits = []
        root.loadedCount = 0
        root.hasMore = true
        root.searchMode = false
        root.loading = false
        root.searchDeepening = false
        root.refreshing = false
        root.refreshPending = false
        root.timelineRefreshPending = false
        root.timelinePendingLog = null
        root.refreshCount = 0
        // Timeline 实例没有重建，保留视口引用才能捕获刷新后的首个滚动帧。
        root.timelineLastContentY = 0
        root.timelineMotionObserved = false
        root.timelineLastMotionAt = 0
        root.timelineLastWheelAt = 0
        root.timelineTraceHasContentSample = false
        root.timelineTraceHasSmoothSample = false
        root.timelineTraceLastContentLogAt = 0
        root.timelineTraceLastSmoothLogAt = 0
        root.selectedCommit = null   // 清空选中,避免详情面板显示过期提交
        root.pendingJumpHash = ""
        root.pendingJumpDate = ""
        loadMore()
    }

    function resetForRepoChange() {
        root.currentBranch = ""
        searchInput.text = ""
        resetAndLoad()
    }

    function requestCurrentBranch() {
        if (!GitBridge || !GitBridge.repoPath) {
            root.currentBranch = ""
            return
        }
        GitBridge.requestCurrentBranch()
    }

    function loadMore() {
        if (root.loading || !root.hasMore || root.searchMode) return
        if (!GitBridge || !GitBridge.repoPath) return
        if (root.loadedCount >= root.maxHistoryCommits) {
            root.hasMore = false
            return
        }
        root.loading = true
        // 后台分页获取,结果经 logReady 回填
        GitBridge.requestLog(
            Math.min(root.pageSize, root.maxHistoryCommits - root.loadedCount),
            root.loadedCount, root.includeAllRefs
        )
    }

    // PrismQML 0.4.0.8 的虚拟 ListView 在回收行后会改变 originY，
    // 但 SmoothScrollHelper 的滚动上限可能暂时停在旧 contentHeight。
    // 直接观察视口并补发同一个分页入口，避免只能显示前 300 条。
    function _probeTimelineEnd() {
        if (!root.pageActive || root.searchMode || root.loading || !root.hasMore)
            return
        if (!root.timelineViewport)
            root.timelineViewport = root._findTimelineViewportForProbe(root)
        var viewport = root.timelineViewport
        if (!viewport) return
        var contentHeight = Number(viewport.contentHeight)
        var viewportHeight = Number(viewport.height)
        var contentY = Number(viewport.contentY)
        var originY = Number(viewport.originY)
        if (!isFinite(contentHeight) || !isFinite(viewportHeight)
                || !isFinite(contentY) || !isFinite(originY)
                || contentHeight <= viewportHeight) return
        var bottom = originY + contentHeight
        if (contentY + viewportHeight >= bottom - root.timelinePrefetchDistance)
            root._requestTimelineMore()
    }

    function _observeTimelineMotion() {
        root._ensureTimelineViewport()
        var viewport = root.timelineViewport
        if (!viewport) return
        var current = Number(viewport.contentY)
        if (!isFinite(current)) return
        if (root.timelineTraceEnabled) {
            var traceNow = Date.now()
            var traceDelta = root.timelineTraceHasContentSample
                ? current - root.timelineTraceLastLoggedContentY : 0
            var directionFlip = root.timelineTraceHasContentSample
                && Math.abs(traceDelta) > 0.01
                && Math.abs(root.timelineTraceLastDelta) > 0.01
                && traceDelta * root.timelineTraceLastDelta < 0
            if (!root.timelineTraceHasContentSample || directionFlip
                    || Math.abs(traceDelta) >= 4
                    || traceNow - root.timelineTraceLastContentLogAt >= 100) {
                root._timelineTrace(
                    "viewport.contentY",
                    "y=" + current.toFixed(2)
                        + " delta=" + traceDelta.toFixed(2)
                        + " directionFlip=" + directionFlip
                )
                root.timelineTraceLastContentLogAt = traceNow
            }
            root.timelineTraceLastLoggedContentY = current
            root.timelineTraceLastDelta = traceDelta
            root.timelineTraceHasContentSample = true
        }
        if (!root.timelineMotionObserved) {
            root.timelineLastContentY = current
            root.timelineMotionObserved = true
            root.timelineLastMotionAt = Date.now()
            return
        }
        var delta = current - root.timelineLastContentY
        if (Math.abs(delta) > 0.01) {
            root.timelineLastMotionAt = Date.now()
            if (root.timelineRefreshPending)
                timelineRefreshAfterMotion.restart()
            if (root.timelinePendingLog !== null)
                timelineLogAfterMotion.restart()
        }
        root.timelineLastContentY = current
    }

    function _timelineScrollIdle() {
        var lastActivityAt = Math.max(
            root.timelineLastMotionAt, root.timelineLastWheelAt
        )
        if (lastActivityAt <= 0) return true
        return Date.now() - lastActivityAt
            >= root.timelineQuietPeriod
    }

    function _observeTimelineWheel() {
        root._ensureTimelineViewport()
        root.timelineLastWheelAt = Date.now()
        if (root.timelineTraceEnabled) {
            root._timelineTrace(
                "wheel",
                "lastWheelAt=" + root.timelineLastWheelAt
            )
        }
        if (root.timelineRefreshPending)
            timelineRefreshAfterMotion.restart()
        if (root.timelinePendingLog !== null)
            timelineLogAfterMotion.restart()
    }

    function _observeTimelineSmoothPos(value) {
        if (!root.timelineTraceEnabled) return
        var current = Number(value)
        if (!isFinite(current)) return
        var now = Date.now()
        var delta = root.timelineTraceHasSmoothSample
            ? current - root.timelineTraceLastLoggedSmoothPos : 0
        var directionFlip = root.timelineTraceHasSmoothSample
            && Math.abs(delta) > 0.01
            && Math.abs(root.timelineTraceLastSmoothDelta) > 0.01
            && delta * root.timelineTraceLastSmoothDelta < 0
        if (!root.timelineTraceHasSmoothSample || directionFlip
                || Math.abs(delta) >= 8
                || now - root.timelineTraceLastSmoothLogAt >= 120) {
            root._timelineTrace(
                "helper.smoothPos",
                "value=" + current.toFixed(2)
                    + " delta=" + delta.toFixed(2)
                    + " directionFlip=" + directionFlip
            )
            root.timelineTraceLastSmoothLogAt = now
        }
        root.timelineTraceLastLoggedSmoothPos = current
        root.timelineTraceLastSmoothDelta = delta
        root.timelineTraceHasSmoothSample = true
    }

    function _requestTimelineMore() {
        root._ensureTimelineViewport()
        // Request at the prefetch edge. Pagination responses append immediately;
        // refresh replacements are the only results deferred by _handleLogReady.
        // 到达预取线立即请求;分页结果直接追加,只有刷新替换会由 _handleLogReady 延后。
        root.loadMore()
    }

    function _ensureTimelineViewport() {
        if (!root.timelineViewport)
            root.timelineViewport = root._findTimelineViewportForProbe(root)
        return root.timelineViewport
    }

    function _sameCommitRefs(left, right) {
        var first = left || []
        var second = right || []
        if (first.length !== second.length) return false
        for (var index = 0; index < first.length; index++) {
            if ((first[index].name || "") !== (second[index].name || "")
                    || (first[index].kind || "") !== (second[index].kind || ""))
                return false
        }
        return true
    }

    function _sameTimelineCommits(left, right) {
        var current = left || []
        var incoming = right || []
        if (current.length !== incoming.length) return false
        for (var index = 0; index < current.length; index++) {
            var first = current[index] || {}
            var second = incoming[index] || {}
            if ((first.hash || "") !== (second.hash || "")
                    || (first.revertedBy || "") !== (second.revertedBy || "")
                    || (first.reverts || "") !== (second.reverts || "")
                    || !root._sameCommitRefs(first.refs, second.refs))
                return false
        }
        return true
    }

    function _applyLogReady(repoPath, skip, batch) {
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "log.apply.enter",
                "skip=" + skip + " batch=" + (batch || []).length
                    + " commits=" + root.allCommits.length
                    + " loading=" + root.loading
                    + " refreshing=" + root.refreshing
            )
        // 任何过期/不匹配分支都要解锁 loading,否则切仓库后再也无法加载
        if (!GitBridge || repoPath !== GitBridge.repoPath) {
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "log.apply.drop", "reason=repo_mismatch skip=" + skip
                )
            root.loading = false
            root.refreshing = false
            return
        }
        // 搜索请求使用独立的后端序列号,旧的分页响应不能覆盖搜索结果。
        if (root.searchMode) {
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "log.apply.drop", "reason=search_mode skip=" + skip
                )
            return
        }
        if (root.refreshing) {
            if (skip !== 0) {
                if (root.timelineTraceEnabled)
                    root._timelineTrace(
                        "log.apply.drop",
                        "reason=refresh_nonzero_skip skip=" + skip
                    )
                root.loading = false
                root.refreshing = false
                return
            }
            var historyChanged = !root._sameTimelineCommits(
                root.allCommits, batch
            )
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "log.apply.refresh_decision",
                    "historyChanged=" + historyChanged
                        + " before=" + root.allCommits.length
                        + " incoming=" + batch.length
                )
            if (historyChanged) root.allCommits = batch
            root.loadedCount = batch.length
            root.hasMore = batch.length === root.refreshCount
                && root.loadedCount < root.maxHistoryCommits
            root.finishLoading()
            root.refreshing = false
            if (historyChanged) root._restoreSelection(batch)
            root._schedulePendingDateJump()
            if (root.timelineTraceEnabled) {
                root._timelineTrace(
                    "log.apply.refresh_done",
                    "historyChanged=" + historyChanged
                        + " commits=" + root.allCommits.length
                )
            }
            return
        }
        if (skip !== root.loadedCount) {
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "log.apply.drop",
                    "reason=skip_mismatch skip=" + skip
                        + " loaded=" + root.loadedCount
                )
            root.loading = false
            return
        }
        var remaining = root.maxHistoryCommits - root.loadedCount
        var nextBatch = batch.slice(0, Math.max(0, remaining))
        root.allCommits = root.allCommits.concat(nextBatch)
        root.loadedCount += nextBatch.length
        root.hasMore = batch.length === root.pageSize
            && root.loadedCount < root.maxHistoryCommits
        root.finishLoading()
        root._schedulePendingDateJump()
        if (root.timelineTraceEnabled) {
            root._timelineTrace(
                "log.apply.append_done",
                "skip=" + skip + " appended=" + nextBatch.length
                    + " commits=" + root.allCommits.length
            )
        }
    }

    function _handleLogReady(repoPath, skip, batch) {
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "log.ready",
                "skip=" + skip + " batch=" + (batch || []).length
                    + " idle=" + root._timelineScrollIdle()
                    + " refreshing=" + root.refreshing
            )
        if (!GitBridge || repoPath !== GitBridge.repoPath) {
            if (root.timelineTraceEnabled)
                root._timelineTrace("log.ready.drop", "reason=repo_mismatch")
            root.loading = false
            root.refreshing = false
            return
        }
        if (root.searchMode) {
            if (root.timelineTraceEnabled)
                root._timelineTrace("log.ready.drop", "reason=search_mode")
            return
        }
        root._ensureTimelineViewport()
        // Pagination appends rows and is safe while the engine keeps the logical
        // viewport in bounds. Only a refresh replacement must wait for quiescence.
        // 分页只是追加行,引擎已保证逻辑视口合法,滚动中可直接应用；只有刷新替换需等静默。
        var deferUntilIdle = !root._timelineScrollIdle()
            && (root.refreshing || skip === 0)
        if (deferUntilIdle) {
            root.timelinePendingLog = {
                "repoPath": repoPath,
                "skip": skip,
                "batch": batch
            }
            timelineLogAfterMotion.restart()
            if (root.timelineTraceEnabled) {
                root._timelineTrace(
                    "log.ready.defer",
                    "skip=" + skip + " batch=" + batch.length
                        + " quietPeriod=" + root.timelineQuietPeriod
                )
            }
            return
        }
        if (root.timelineTraceEnabled)
            root._timelineTrace("log.ready.apply_now", "skip=" + skip)
        root._applyLogReady(repoPath, skip, batch)
    }

    function _findTimelineViewportForProbe(item) {
        if (!item) return null
        if (item.objectName === "timelineVirtualViewport") return item
        var children = item.children || []
        for (var index = 0; index < children.length; index++) {
            var found = root._findTimelineViewportForProbe(children[index])
            if (found) return found
        }
        return null
    }

    Connections {
        target: root.timelineViewport
        ignoreUnknownSignals: true
        function onContentYChanged() { root._observeTimelineMotion() }
        function onContentHeightChanged() {
            if (!root.timelineTraceEnabled) return
            var viewport = root.timelineViewport
            if (viewport)
                root._timelineTrace(
                    "viewport.contentHeightChanged",
                    "value=" + Number(viewport.contentHeight).toFixed(2)
                )
        }
        function onOriginYChanged() {
            if (!root.timelineTraceEnabled) return
            var viewport = root.timelineViewport
            if (viewport)
                root._timelineTrace(
                    "viewport.originYChanged",
                    "value=" + Number(viewport.originY).toFixed(2)
                )
        }
        function onHeightChanged() {
            if (!root.timelineTraceEnabled) return
            var viewport = root.timelineViewport
            if (viewport)
                root._timelineTrace(
                    "viewport.heightChanged",
                    "value=" + Number(viewport.height).toFixed(2)
                )
        }
    }

    Connections {
        target: root.timelineScrollHelper
        enabled: root.timelineTraceEnabled
        ignoreUnknownSignals: true
        function onTargetPosChanged() {
            var helper = root.timelineScrollHelper
            if (helper)
                root._timelineTrace(
                    "helper.targetPos",
                    "value=" + Number(helper.targetPos).toFixed(2)
                )
        }
        function onSmoothPosChanged() {
            var helper = root.timelineScrollHelper
            if (helper) root._observeTimelineSmoothPos(helper.smoothPos)
        }
        function onIsOvershotChanged() {
            var helper = root.timelineScrollHelper
            if (helper)
                root._timelineTrace(
                    "helper.isOvershot", "value=" + helper.isOvershot
                )
        }
        function onMinScrollChanged() {
            var helper = root.timelineScrollHelper
            if (helper)
                root._timelineTrace(
                    "helper.minScroll",
                    "value=" + Number(helper.minScroll).toFixed(2)
                )
        }
        function onMaxScrollChanged() {
            var helper = root.timelineScrollHelper
            if (helper)
                root._timelineTrace(
                    "helper.maxScroll",
                    "value=" + Number(helper.maxScroll).toFixed(2)
                )
        }
    }

    WheelHandler {
        parent: root.timelineViewport || root
        enabled: root.timelineViewport !== null
        target: null
        blocking: false
        activeTimeout: root.timelineQuietPeriod / 1000
        onWheel: function(event) { root._observeTimelineWheel() }
    }

    // 仓库状态变化时保留当前时间线,后台重新拉取已加载范围。
    // 只有新数据返回后才替换数组,避免异步请求期间整个页面先变空。
    function refreshIncrementally() {
        if (!GitBridge || !GitBridge.repoPath) {
            if (root.timelineTraceEnabled)
                root._timelineTrace("refresh.enter", "ignored=no_repo")
            return
        }
        root._ensureTimelineViewport()
        var idle = root._timelineScrollIdle()
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "refresh.enter",
                "idle=" + idle + " loading=" + root.loading
                    + " refreshing=" + root.refreshing
                    + " commits=" + root.allCommits.length
                    + " pending=" + root.timelineRefreshPending
            )
        if (!idle) {
            root.timelineRefreshPending = true
            timelineRefreshAfterMotion.restart()
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "refresh.defer", "reason=scroll_active quietPeriod="
                        + root.timelineQuietPeriod
                )
            return
        }
        root.timelineRefreshPending = false
        if (root.loading) {
            root.refreshPending = true
            if (root.timelineTraceEnabled)
                root._timelineTrace("refresh.defer", "reason=loading")
            return
        }
        requestCurrentBranch()
        if (root.searchMode) {
            if (searchInput.text === "") {
                if (root.timelineTraceEnabled)
                    root._timelineTrace("refresh.route", "mode=reset")
                resetAndLoad()
                return
            }
            root.refreshing = true
            root.loading = true
            root.searchDeepening = false
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "refresh.request_search",
                    "query=" + searchInput.text
                        + " includeAllRefs=" + root.includeAllRefs
                )
            GitBridge.requestSearch(
                searchInput.text, "all", root.includeAllRefs
            )
            return
        }
        root.refreshing = true
        root.loading = true
        root.refreshCount = Math.min(
            root.maxHistoryCommits,
            Math.max(root.pageSize, root.loadedCount)
        )
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "refresh.request_log",
                "count=" + root.refreshCount + " skip=0"
                    + " includeAllRefs=" + root.includeAllRefs
            )
        GitBridge.requestLog(root.refreshCount, 0, root.includeAllRefs)
    }

    function finishLoading() {
        root.loading = false
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "loading.finished",
                "refreshPending=" + root.refreshPending
                    + " commits=" + root.allCommits.length
            )
        if (!root.refreshPending) return
        root.refreshPending = false
        if (root.timelineTraceEnabled)
            root._timelineTrace("refresh.pending_replay")
        Qt.callLater(function() { root.refreshIncrementally() })
    }

    function _restoreSelection(commits) {
        if (!root.selectedCommit) return
        var selectedHash = root.selectedCommit.hash || ""
        for (var index = 0; index < commits.length; index++) {
            if ((commits[index].hash || "") === selectedHash) {
                root.selectedCommit = commits[index]
                return
            }
        }
        // 提交已被 reset/改写时,详情面板不能继续展示过期数据。
        root.selectedCommit = null
    }

    // Timeline 会按组/卡片签名区分尾部追加与内容替换，直接交给它增量同步。
    // 不先发空模型，避免异步刷新在滚轮越界期间把视口瞬间夹回起点。
    function _syncRenderedTimelineItems() {
        var nextItems = root.timelineItems || []
        var nextCount = root.allCommits.length
        var nextTopHash = nextCount > 0 ? (root.allCommits[0].hash || "") : ""
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "timeline.sync.enter",
                "items=" + nextItems.length + " commits=" + nextCount
                    + " previousRendered=" + root.renderedTimelineCommitCount
            )
        root.renderedTimelineItems = nextItems
        root.renderedTimelineCommitCount = nextCount
        root.renderedTimelineTopHash = nextTopHash
        if (root.timelineTraceEnabled) {
            root._timelineTrace(
                "timeline.sync.assigned",
                "items=" + nextItems.length + " commits=" + nextCount
            )
        }
    }

    onTimelineItemsChanged: {
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "timelineItems.changed",
                "items=" + (root.timelineItems || []).length
            )
        root._syncRenderedTimelineItems()
    }

    onAllCommitsChanged: {
        if (!root.timelineTraceEnabled) return
        root._timelineTrace(
            "allCommits.changed", "length=" + root.allCommits.length
        )
    }

    function doSearch(query) {
        if (query === "") { resetAndLoad(); return }
        if (!GitBridge || !GitBridge.repoPath) return
        // 进入/切换搜索模式时保留旧结果,待异步结果返回后再替换,避免闪空。
        root.loadedCount = 0
        root.hasMore = false        // 搜索结果不分页
        root.loading = true
        root.searchDeepening = false
        root.refreshing = false
        root.refreshPending = false
        root.timelineRefreshPending = false
        root.timelinePendingLog = null
        root.searchMode = true
        root.selectedCommit = null
        GitBridge.requestSearch(query, "all", root.includeAllRefs)
    }

    function setHistoryScope(scopeIndex) {
        var nextIncludeAllRefs = scopeIndex === 1
        if (root.includeAllRefs === nextIncludeAllRefs) return
        root.includeAllRefs = nextIncludeAllRefs
        if (searchInput.text.trim() !== "")
            root.doSearch(searchInput.text)
        else
            root.resetAndLoad()
    }

    function jumpToCommit(hash) {
        var targetHash = (hash || "").trim()
        if (targetHash === "") return
        root.pendingJumpHash = targetHash.toLowerCase()
        if (searchInput.text === targetHash)
            root.doSearch(targetHash)
        else
            searchInput.text = targetHash
    }

    function _dateText(year, month, day) {
        var pad = function(value) { return value < 10 ? "0" + value : "" + value }
        return year + "-" + pad(month) + "-" + pad(day)
    }

    function _groupDate(group) {
        if (group && group.dateKey) return group.dateKey
        var cards = group && group.cards ? group.cards : []
        if (cards.length > 0 && cards[0].commit)
            return (cards[0].commit.date || "").substring(0, 10)
        return ""
    }

    function _dateGroupForJump(targetDate) {
        var groups = root.timelineItems || []
        var precedingIndex = -1
        for (var index = 0; index < groups.length; index++) {
            var date = root._groupDate(groups[index])
            if (date === targetDate)
                return { "index": index, "exact": true }
            if (precedingIndex < 0 && date !== "" && date < targetDate)
                precedingIndex = index
        }
        if (precedingIndex >= 0)
            return { "index": precedingIndex, "exact": false }
        if (groups.length === 0) return { "index": -1, "exact": false }
        var firstDate = root._groupDate(groups[0])
        return {
            "index": firstDate !== "" && targetDate > firstDate
                ? 0 : groups.length - 1,
            "exact": false
        }
    }

    function _groupRowIndex(groupIndex) {
        var groups = root.timelineItems || []
        var rowIndex = 0
        for (var index = 0; index < groupIndex; index++)
            rowIndex += 1 + ((groups[index].cards || []).length)
        return rowIndex
    }

    function _findDateJumpViewport(item) {
        if (!item) return null
        if (item.objectName === "timelineVirtualViewport") return item
        var children = item.children || []
        for (var index = 0; index < children.length; index++) {
            var found = root._findDateJumpViewport(children[index])
            if (found) return found
        }
        return null
    }

    function _schedulePendingDateJump() {
        if (root.pendingJumpDate === "") return
        Qt.callLater(function() {
            if (root.pendingJumpDate !== "") root._attemptDateJump()
        })
    }

    function _attemptDateJump() {
        var targetDate = root.pendingJumpDate
        if (targetDate === "" || root.loading || root.searchDeepening) return

        var groups = root.timelineItems || []
        if (groups.length === 0) {
            if (root.hasMore && !root.searchMode) root.loadMore()
            return
        }

        var oldestDate = root._groupDate(groups[groups.length - 1])
        if (!root.searchMode && root.hasMore && oldestDate !== ""
                && targetDate < oldestDate) {
            root.loadMore()
            return
        }

        var match = root._dateGroupForJump(targetDate)
        if (match.index < 0) {
            root.pendingJumpDate = ""
            return
        }
        var viewport = root._findDateJumpViewport(root)
        var rowIndex = root._groupRowIndex(match.index)
        if (!viewport || viewport.count <= rowIndex) {
            root._schedulePendingDateJump()
            return
        }
        viewport.positionViewAtIndex(rowIndex, ListView.Beginning)
        root.pendingJumpDate = ""
    }

    function jumpToDate(year, month, day) {
        root.pendingJumpDate = root._dateText(year, month, day)
        root._attemptDateJump()
    }

    function _selectPendingJump(results) {
        if (root.pendingJumpHash === "") return
        var targetHash = root.pendingJumpHash
        root.pendingJumpHash = ""
        for (var i = 0; i < results.length; i++) {
            if ((results[i].hash || "").toLowerCase() === targetHash) {
                root.selectedCommit = results[i]
                return
            }
        }
        var scopeText = root.includeAllRefs
            ? "关联提交不在任何分支历史中"
            : "关联提交不在当前分支历史中"
        Fluent.NotificationManager.desktop.error("无法跳转", scopeText)
    }

    Connections {
        target: GitBridge
        function onLogReady(repoPath, skip, batch) {
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "signal.logReady",
                    "skip=" + skip + " batch=" + (batch || []).length
                )
            root._handleLogReady(repoPath, skip, batch)
        }
        function onSearchReady(repoPath, results) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) {
                root.loading = false
                root.searchDeepening = false
                root.refreshing = false
                return
            }
            if (!root.searchMode) return  // 已退出搜索,丢弃过期搜索结果
            root.allCommits = results
            root.finishLoading()
            root.searchDeepening = false
            root.refreshing = false
            root._restoreSelection(results)
            root._selectPendingJump(results)
            root._schedulePendingDateJump()
        }
        function onSearchPreviewReady(repoPath, results) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return
            if (!root.searchMode) return
            root.allCommits = results
            root.finishLoading()
            root.searchDeepening = true
            root._restoreSelection(results)
        }
    }

    Connections {
        target: GitBridge
        function onStatusChanged() {
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "signal.statusChanged",
                    "commits=" + root.allCommits.length
                        + " loading=" + root.loading
                        + " refreshing=" + root.refreshing
                )
            root.refreshIncrementally()
        }
        function onRepoPathChanged(path) {
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "signal.repoPathChanged", "path=" + path
                )
            cherryPickDialog.close()
            root._clearCherryPickDialogState()
            root.resetForRepoChange()
        }
        function onBranchReady(repoPath, branch) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return
            root.currentBranch = branch
            if (root.cherryPickRequestRepoPath !== repoPath) return
            root.cherryPickCurrentBranch = branch
            var targetIndex = root.cherryPickBranches.indexOf(branch)
            if (targetIndex >= 0)
                root.cherryPickTargetBranch = root.cherryPickBranches[targetIndex]
        }
        function onBranchesReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath
                    || repoPath !== root.cherryPickRequestRepoPath) return
            var names = []
            for (var i = 0; i < list.length; i++) {
                var branch = list[i]
                // 分离头指针展示项不是可检出的本地分支，不能作为目标。
                if (!branch.isRemote && branch.name.indexOf(" ") < 0)
                    names.push(branch.name)
            }
            root.cherryPickBranches = names
            var targetIndex = names.indexOf(root.cherryPickCurrentBranch)
            if (targetIndex < 0 && names.length > 0) targetIndex = 0
            root.cherryPickTargetBranch = targetIndex >= 0 ? names[targetIndex] : ""
        }
    }

    function _op(task) {
        if (!task) return
        task.succeeded.connect(function(result) {
            if (result && result[0]) root.refreshIncrementally()
        })
    }

    function _openCherryPickDialog() {
        if (!root.selectedCommit || !GitBridge || !GitBridge.repoPath) return
        root.cherryPickRequestRepoPath = GitBridge.repoPath
        root.cherryPickCurrentBranch = ""
        root.cherryPickBranches = []
        root.cherryPickTargetBranch = ""
        cherryPickDialog.open()
        GitBridge.requestCurrentBranch()
        GitBridge.requestBranches()
    }

    function _clearCherryPickDialogState() {
        root.cherryPickRequestRepoPath = ""
        root.cherryPickBranches = []
        root.cherryPickCurrentBranch = ""
        root.cherryPickTargetBranch = ""
    }

    // 弹 reset 危险确认(按模式给不同说明,hard 额外强警告)
    function _askReset(mode) {
        if (!root.selectedCommit) return
        var desc = {
            "soft": "(soft 模式:保留暂存区和工作区的所有改动,仅移动 HEAD)",
            "mixed": "(mixed 模式:保留工作区改动,清空暂存区)",
            "hard": "⚠️ (hard 模式:丢弃工作区和暂存区的所有未提交改动,不可恢复!)"
        }[mode]
        resetDanger.content = "将回滚到提交 " + root.selectedCommit.shortHash
            + "\n" + desc + "\n此操作会改变提交历史。"
        resetDanger._hash = root.selectedCommit.hash
        resetDanger._mode = mode
        resetDanger.start()
    }

    onPageActiveChanged: {
        if (root.timelineTraceEnabled)
            root._timelineTrace(
                "pageActive.changed", "active=" + root.pageActive
            )
        if (!root.pageActive || !root.initialized) return
        Qt.callLater(function() {
            if (root.pageActive) root.refreshIncrementally()
        })
    }

    Component.onCompleted: {
        root.initialized = true
        root.timelineViewport = root._findTimelineViewportForProbe(root)
        if (root.timelineTraceEnabled) {
            root._timelineTrace(
                "view.completed",
                "viewport=" + (root.timelineViewport !== null)
                    + " commits=" + root.allCommits.length
            )
            root._ensureTimelineTraceObjects()
            root._timelineTrace(
                "helper.bound",
                "available=" + (root.timelineScrollHelper !== null)
            )
        }
        root._syncRenderedTimelineItems()
        root.resetAndLoad()
    }

    Timer {
        id: timelineEndProbe
        interval: 200
        repeat: true
        running: root.pageActive && root.initialized
        onTriggered: root._probeTimelineEnd()
    }

    Timer {
        id: timelineRefreshAfterMotion
        interval: root.timelineQuietPeriod
        repeat: false
        onTriggered: {
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "refresh.timer", "pending=" + root.timelineRefreshPending
                )
            if (!root.timelineRefreshPending) return
            if (!root._timelineScrollIdle()) {
                if (root.timelineTraceEnabled)
                    root._timelineTrace(
                        "refresh.timer.defer", "reason=still_active"
                    )
                restart()
                return
            }
            root.timelineRefreshPending = false
            if (root.timelineTraceEnabled)
                root._timelineTrace("refresh.timer.apply")
            root.refreshIncrementally()
        }
    }

    Timer {
        id: timelineLogAfterMotion
        interval: root.timelineQuietPeriod
        repeat: false
        onTriggered: {
            var pending = root.timelinePendingLog
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "log.timer",
                    "hasPending=" + (pending !== null)
                )
            if (pending === null) return
            if (!root._timelineScrollIdle()) {
                if (root.timelineTraceEnabled)
                    root._timelineTrace("log.timer.defer", "reason=still_active")
                restart()
                return
            }
            root.timelinePendingLog = null
            if (root.timelineTraceEnabled)
                root._timelineTrace(
                    "log.timer.apply", "skip=" + pending.skip
                )
            root._applyLogReady(
                pending.repoPath, pending.skip, pending.batch
            )
        }
    }

    CommitTimelineModel {
        id: historyTimelineModel
        commits: root.allCommits
    }

    // ==================== 布局 ====================
    Fluent.SplitPane {
        id: historySplitPane
        objectName: "historySplitPane"

        // 首栏使用稳定的两行布局，不能再用整行 implicitWidth
        // 作为分栏最小值，否则默认窗口会把右侧详情区挤到不可用。
        readonly property real minimumFirstPaneWidth: 520
        readonly property real minimumSecondPaneWidth: 360

        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        orientation: Qt.Horizontal
        splitPosition: 0.55
        firstMinimumSize: minimumFirstPaneWidth
        secondMinimumSize: minimumSecondPaneWidth

        firstContent: Item {
            anchors.fill: parent

            ColumnLayout {
                anchors.fill: parent
                anchors.rightMargin: Fluent.Enums.spacing.m
                spacing: Fluent.Enums.spacing.m

                // 标题信息与筛选控件固定分组，避免 Flow 按 implicitWidth 漂移换行。
                RowLayout {
                    id: historyHeader
                    objectName: "historyHeader"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: Fluent.Enums.spacing.m

                    ColumnLayout {
                        objectName: "historyHeaderInfo"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        spacing: 0
                        Text {
                            Layout.fillWidth: true
                            text: "历史"
                            font.pixelSize: Fluent.Enums.typography.metric
                            font.bold: true
                            color: Fluent.Enums.textColor.primary
                            font.family: Fluent.Enums.fontFamily
                            elide: Text.ElideRight
                        }
                        Text {
                            Layout.fillWidth: true
                            text: (root.searchMode
                                ? root.allCommits.length + " 条搜索结果"
                                : root.allCommits.length + " 条提交")
                                + (root.includeAllRefs
                                    ? " · 全部分支"
                                    : " · 当前分支: "
                                        + (root.currentBranch || "正在读取…"))
                                + (root.searchDeepening ? " · 后台补全中" : "")
                            font.pixelSize: Fluent.Enums.typography.caption
                            color: Fluent.Enums.textColor.tertiary
                            font.family: Fluent.Enums.fontFamily
                            elide: Text.ElideRight
                        }
                    }
                    Fluent.ComboBox {
                        id: historyScopeCombo
                        objectName: "historyScopeCombo"
                        Layout.preferredWidth: 176
                        Layout.minimumWidth: 136
                        Layout.maximumWidth: 176
                        model: [
                            "当前分支",
                            "全部分支"
                        ]
                        currentIndex: root.includeAllRefs ? 1 : 0
                        onActivated: function(scopeIndex) {
                            root.setHistoryScope(scopeIndex)
                        }
                    }
                    Fluent.CalendarPicker {
                        id: historyDatePicker
                        objectName: "historyDatePicker"
                        Layout.preferredWidth: 148
                        Layout.minimumWidth: 132
                        Layout.maximumWidth: 148
                        hasDate: false
                        placeholderText: "跳转日期"
                        onDateChanged: function(year, month, day) {
                            root.jumpToDate(year, month, day)
                        }
                    }
                }

                RowLayout {
                    id: historySearchRow
                    objectName: "historySearchRow"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: Fluent.Enums.spacing.s

                    Fluent.LineEdit {
                        id: searchInput
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.preferredWidth: root.width < 1200 ? 160 : 240
                        placeholderText: "搜索提交(消息/作者/哈希/文件/增删内容)"
                        onTextChanged: searchDebounce.restart()
                    }
                    Fluent.Button {
                        objectName: "historyReflogButton"
                        text: "Reflog"
                        icon: Fluent.Enums.icon.history
                        onClicked: reflogDialog.openReflog()
                    }
                }

                Timer {
                    id: searchDebounce
                    interval: 300
                    onTriggered: root.doSearch(searchInput.text)
                }

                // 提交时间线(虚拟滚动,Timeline 自身 ListView 滚动+只渲染可见项,大列表不卡)
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    Rectangle {
                        id: timelineSurface

                        objectName: "historyTimelineSurface"
                        anchors.fill: parent
                        radius: Fluent.Enums.radius.large
                        color: Fluent.Enums.surfaceColor
                        border.width: Fluent.Enums.border.thin
                        border.color: Fluent.Enums.stateColor.borderLight
                    }

                    Fluent.Timeline {
                        id: historyTimeline
                        objectName: "historyTimeline"
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.m
                        type: Fluent.Enums.timeline.type_graph
                        virtualized: true
                        graphLaneCount: root.graphLaneCount
                        items: root.renderedTimelineItems
                        selectedRole: "hash"
                        selectedKey: root.selectedCommit ? root.selectedCommit.hash : undefined
                        onCardClickedData: function(groupIndex, cardIndex, cardData) {
                            if (cardData && cardData.commit)
                                root.selectedCommit = cardData.commit
                        }
                        onReachedEnd: {
                            if (root.timelineTraceEnabled)
                                root._timelineTrace(
                                    "timeline.reachedEnd",
                                    "loading=" + root.loading
                                        + " hasMore=" + root.hasMore
                                )
                            if (!root.loading && root.hasMore && !root.searchMode)
                                root._requestTimelineMore()
                        }
                    }

                    // 加载状态提示(底部浮层)
                    Text {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottomMargin: Fluent.Enums.spacing.s
                        visible: root.loading
                        text: "加载中..."
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                    }
                }
            }
        }

        secondContent: Item {
            anchors.fill: parent

            Rectangle {
                anchors.fill: parent
                anchors.leftMargin: Fluent.Enums.spacing.m
                radius: Fluent.Enums.radius.large
                color: Fluent.Enums.cardColor
                border.width: Fluent.Enums.border.normal
                border.color: Fluent.Enums.stateColor.border

                // 空状态
                Fluent.EmptyState {
                    anchors.centerIn: parent
                    visible: !root.selectedCommit
                    icon: Fluent.Enums.icon.history
                    title: "未选择提交"
                    description: "从左侧时间线选择一个提交查看详情"
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Fluent.Enums.spacing.xl
                    spacing: Fluent.Enums.spacing.l
                    visible: !!root.selectedCommit

                    // ── 头部:作者头像 + 提交标题 ──
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m

                        Fluent.Avatar {
                            size: 44
                            text: root.selectedCommit ? root.selectedCommit.author : ""
                            Layout.alignment: Qt.AlignTop
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.xs
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.message : ""
                                color: Fluent.Enums.textColor.primary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.title
                                font.bold: true
                                wrapMode: Text.WordWrap
                            }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.author : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                            }
                            RowLayout {
                                visible: root.selectedCommit && !!root.selectedCommit.revertedBy
                                spacing: Fluent.Enums.spacing.xs
                                Fluent.Tag {
                                    status: Fluent.Enums.statusLevel.warning
                                    text: "已撤销"
                                }
                                Text {
                                    text: "由"
                                    color: Fluent.Enums.textColor.secondary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.bodySmall
                                }
                                Fluent.Button {
                                    text: root.selectedCommit
                                        ? root.selectedCommit.revertedBy.substring(0, 8) : ""
                                    style: Fluent.Enums.button.style_hyperlink
                                    onClicked: root.jumpToCommit(root.selectedCommit.revertedBy)
                                }
                                Text {
                                    text: "撤销"
                                    color: Fluent.Enums.textColor.secondary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.bodySmall
                                }
                            }
                            RowLayout {
                                visible: root.selectedCommit && !!root.selectedCommit.reverts
                                spacing: Fluent.Enums.spacing.xs
                                Fluent.Tag {
                                    status: Fluent.Enums.statusLevel.info
                                    text: "Revert"
                                }
                                Text {
                                    text: "撤销了"
                                    color: Fluent.Enums.textColor.secondary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.bodySmall
                                }
                                Fluent.Button {
                                    text: root.selectedCommit
                                        ? root.selectedCommit.reverts.substring(0, 8) : ""
                                    style: Fluent.Enums.button.style_hyperlink
                                    onClicked: root.jumpToCommit(root.selectedCommit.reverts)
                                }
                            }
                        }
                    }

                    Fluent.Separator { Layout.fillWidth: true }

                    // ── 元信息:图标 + 标签 + 值 ──
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m

                        // Hash(等宽,可点复制)
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Icon { icon: Fluent.Enums.icon.code; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.hash : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: "Consolas, monospace"
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                                elide: Text.ElideRight
                            }
                        }
                        // 作者邮箱
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Icon { icon: Fluent.Enums.icon.person; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? (root.selectedCommit.email || root.selectedCommit.author) : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                                elide: Text.ElideRight
                            }
                        }
                        // 时间
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Icon { icon: Fluent.Enums.icon.clock; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Text {
                                Layout.fillWidth: true
                                text: root.selectedCommit ? root.selectedCommit.date : ""
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.bodySmall
                            }
                        }
                        // 分支(有才显示,用 Tag)
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            visible: root.selectedCommit && root.selectedCommit.branch !== ""
                            Fluent.Icon { icon: Fluent.Enums.icon.branch; size: 16; color: Fluent.Enums.textColor.tertiary; Layout.alignment: Qt.AlignVCenter }
                            Fluent.Tag {
                                status: Fluent.Enums.statusLevel.info
                                text: root.selectedCommit ? root.selectedCommit.branch : ""
                            }
                        }
                    }

                    // ── 变更概览:状态统计 + 文件列表 ──
                    CommitFilesPanel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 140
                        commit: root.selectedCommit
                    }

                    Fluent.Separator { Layout.fillWidth: true }

                    // ── 操作区 ──
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Fluent.Enums.spacing.m

                        // 常规操作:自然宽度左对齐(不铺满,更精致),风格统一
                        Flow {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.s
                            Fluent.Button {
                                text: "检出提交"
                                toolTipText: "Checkout"
                                icon: Fluent.Enums.icon.checkmark_circle
                                onClicked: root._op(GitBridge.checkoutCommit(root.selectedCommit.hash))
                            }
                            Fluent.Button {
                                text: "新建分支"
                                icon: Fluent.Enums.icon.branch_fork
                                onClicked: createBranchDialog.openFor(
                                    root.selectedCommit.hash, false)
                            }
                            Fluent.Button {
                                text: "拣选提交"
                                toolTipText: "Cherry-pick"
                                icon: Fluent.Enums.icon.branch
                                onClicked: root._openCherryPickDialog()
                            }
                            Fluent.Button {
                                text: "撤销提交"
                                toolTipText: "Revert"
                                icon: Fluent.Enums.icon.arrow_undo
                                onClicked: root._op(GitBridge.revertCommit(root.selectedCommit.hash))
                            }
                        }

                        Fluent.Separator { Layout.fillWidth: true }

                        // 辅助(左,轻量文字按钮) + 危险操作(右,强调)
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.xs
                            Fluent.Button {
                                text: "复制 Hash"
                                icon: Fluent.Enums.icon.copy
                                style: Fluent.Enums.button.style_transparent
                                onClicked: if (root.selectedCommit && ClipboardHelper) ClipboardHelper.copy(root.selectedCommit.hash)
                            }
                            Fluent.Button {
                                text: "详情"
                                icon: Fluent.Enums.icon.code
                                style: Fluent.Enums.button.style_transparent
                                onClicked: if (root.selectedCommit) commitDetailDialog.openFor(root.selectedCommit.hash)
                            }
                            Item { Layout.fillWidth: true }
                            Fluent.Button {
                                text: "重置"
                                toolTipText: "Reset"
                                icon: Fluent.Enums.icon.arrow_clockwise
                                style: Fluent.Enums.button.style_primary
                                // 下拉选 reset 模式;选任一模式都走危险确认(hard 额外警告)
                                feature: Fluent.Enums.button.feature_dropdown
                                menuItems: ["Soft — 保留暂存区+工作区", "Mixed — 保留工作区,清暂存区", "Hard — 丢弃所有改动"]
                                onClicked: root._askReset("mixed")   // 主按钮默认 mixed(最常用)
                                onMenuItemClicked: function(index, text) {
                                    root._askReset(index === 0 ? "soft" : (index === 2 ? "hard" : "mixed"))
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // 危险操作:reset 二次确认(mode 由调用方经 _askReset 设置)
    DangerDialog {
        id: resetDanger
        title: "确认 Reset"
        countdown: 3
        property string _hash: ""
        property string _mode: "mixed"
        onConfirmed: root._op(GitBridge.resetToCommit(_hash, _mode))
    }

    // 提交详情
    CommitDetailDialog { id: commitDetailDialog }

    // Cherry-pick 必须明确显示并选择目标本地分支，避免误以为会应用到提交所属分支。
    Fluent.MessageBox {
        id: cherryPickDialog
        objectName: "cherryPickDialog"
        title: ""
        confirmText: "应用 Cherry-pick"
        cancelText: "取消"
        function validate() {
            return root.selectedCommit !== null
                && root.cherryPickBranches.indexOf(root.cherryPickTargetBranch) >= 0
        }
        onAccepted: {
            var commit = root.selectedCommit
            var target = root.cherryPickTargetBranch
            if (commit && target)
                root._op(GitBridge.cherryPickToBranch(commit.hash, target))
            root._clearCherryPickDialogState()
        }
        onRejected: root._clearCherryPickDialogState()

        ColumnLayout {
            width: 420
            spacing: Fluent.Enums.spacing.m

            DialogTitle {
                objectName: "cherryPickDialogTitle"
                text: "Cherry-pick 提交"
            }

            Text {
                objectName: "cherryPickCommitSummary"
                Layout.fillWidth: true
                text: root.selectedCommit
                    ? root.selectedCommit.shortHash + " · " + root.selectedCommit.message
                    : ""
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideRight
            }

            Fluent.Label {
                objectName: "cherryPickTargetLabel"
                Layout.fillWidth: true
                text: "目标分支"
                type: Fluent.Enums.label.type_body_strong
                color: Fluent.Enums.textColor.secondary
            }

            Fluent.ComboBox {
                id: cherryPickTargetCombo
                objectName: "cherryPickTargetCombo"
                Layout.fillWidth: true
                model: root.cherryPickBranches
                currentIndex: root.cherryPickBranches.indexOf(root.cherryPickTargetBranch)
                placeholderText: "正在加载本地分支…"
                enabled: root.cherryPickBranches.length > 0
                onActivated: function(index) {
                    root.cherryPickTargetBranch = root.cherryPickBranches[index] || ""
                }
            }

            Text {
                objectName: "cherryPickTargetHint"
                Layout.fillWidth: true
                text: root.cherryPickTargetBranch
                    ? (root.cherryPickTargetBranch === root.cherryPickCurrentBranch
                        ? "当前分支: " + root.cherryPickCurrentBranch
                        : "将先切换到 " + root.cherryPickTargetBranch
                            + "，再应用该提交")
                    : "未找到可用的本地目标分支"
                color: root.cherryPickTargetBranch
                    ? Fluent.Enums.textColor.tertiary
                    : Fluent.Enums.statusLevel.warningColor
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                wrapMode: Text.WordWrap
            }
        }
    }

    // 直接从选中的历史提交创建，默认不切换，避免扰动当前工作区。
    CreateBranchDialog {
        id: createBranchDialog
        onOperationSucceeded: root.refreshIncrementally()
    }

    // 引用日志
    ReflogDialog {
        id: reflogDialog
        onCheckoutRequested: function(h) { root._op(GitBridge.checkoutCommit(h)) }
    }
}
