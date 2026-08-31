// RepositoryTabBar - Gitora repository session adapter Gitora 仓库会话适配层
// The visual tab bar is provided by PrismQML; this component owns repository data only.
// 标签视觉由 PrismQML 提供，本组件只负责仓库数据和切换请求。
pragma ComponentBehavior: Bound
import QtQuick
import PrismQML as Fluent

Item {
    id: root

    // ==================== Public Props 公开属性 ====================
    property var gitBridge: null
    property var repoScanner: null
    property bool switchingEnabled: true
    property int tabHeight: Fluent.Enums.controlSize.tableHeaderHeight

    // ==================== Readonly State 只读状态 ====================
    readonly property string activePath: gitBridge ? (gitBridge.repoPath || "") : ""
    readonly property string activePathKey: _pathKey(activePath)
    readonly property int tabCount: _tabs.length

    // ==================== Internal Props 内部属性 ====================
    property var _tabs: []
    property var _pickerPaths: []
    property string _closingActivePath: ""

    // ==================== Signals 信号 ====================
    signal repositorySelected(string path)
    signal repositoryClosed(string path)

    // ==================== Public Methods 公开方法 ====================
    function _pathKey(path) {
        var normalized = String(path || "").replace(/\\/g, "/").replace(/\/+$/, "")
        return Qt.platform.os === "windows" ? normalized.toLowerCase() : normalized
    }

    function _repoName(path) {
        var normalized = String(path || "").replace(/\\/g, "/").replace(/\/+$/, "")
        var parts = normalized.split("/")
        return parts.length > 0 && parts[parts.length - 1] !== ""
            ? parts[parts.length - 1] : normalized
    }

    function _indexForPath(path) {
        var key = _pathKey(path)
        for (var i = 0; i < _tabs.length; i++) {
            if (_pathKey(_tabs[i].path) === key) return i
        }
        return -1
    }

    function _newTab(path) {
        var value = String(path || "")
        return {
            title: _repoName(value),
            icon: Fluent.Enums.icon.folder,
            subtitle: "未读取分支",
            branch: "",
            badgeText: "",
            badgeLevel: Fluent.Enums.statusLevel.info,
            path: value,
            pending: false,
            changeCount: -1,
            repoState: "unknown",
            enabled: true,
            closeEnabled: true
        }
    }

    function _appendPath(path) {
        var value = String(path || "")
        if (value === "" || _indexForPath(value) >= 0)
            return false
        var next = _tabs.slice()
        next.push(_newTab(value))
        _tabs = next
        return true
    }

    function ensurePath(path) { return _appendPath(path) }

    function setOpenedPaths(paths) {
        var values = []
        var seen = ({})
        var candidates = []
        if (activePath !== "") candidates.push(activePath)
        for (var i = 0; i < (paths || []).length; i++) candidates.push(paths[i])

        for (var j = 0; j < candidates.length; j++) {
            var value = String(candidates[j] || "")
            var key = _pathKey(value)
            if (value !== "" && !seen[key]) {
                seen[key] = true
                values.push(value)
            }
        }

        var next = []
        for (var k = 0; k < values.length; k++) next.push(_newTab(values[k]))
        _tabs = next
        _syncCurrentIndex()
    }

    function _updateTab(path, changes) {
        var index = _indexForPath(path)
        if (index < 0) {
            ensurePath(path)
            index = _indexForPath(path)
        }
        if (index < 0) return
        var next = _tabs.slice()
        next[index] = Object.assign({}, next[index], changes || {})
        _tabs = next
    }

    function _syncCurrentIndex() {
        var index = _indexForPath(activePath)
        if (index >= 0 && tabBar.currentIndex !== index) tabBar.currentIndex = index
    }

    function _setPending(path, pending) {
        var index = _indexForPath(path)
        var branch = index >= 0 ? String(_tabs[index].branch || "") : ""
        _updateTab(path, {
            pending: !!pending,
            subtitle: pending ? "打开中…" : (branch || "未读取分支")
        })
    }

    function _updateStatus(path, count) {
        var normalizedCount = Math.max(0, Number(count) || 0)
        _updateTab(path, {
            changeCount: normalizedCount,
            repoState: normalizedCount > 0 ? "dirty" : "clean",
            badgeText: normalizedCount > 0 ? String(normalizedCount) : "干净",
            badgeLevel: normalizedCount > 0
                ? Fluent.Enums.statusLevel.warning : Fluent.Enums.statusLevel.success
        })
    }

    function _updateBranch(path, branch) {
        var value = String(branch || "")
        _updateTab(path, {
            branch: value,
            subtitle: value || "未读取分支"
        })
    }

    function _markOpenFailed(path) {
        _updateTab(path, {
            pending: false,
            repoState: "error",
            subtitle: "无法打开",
            badgeText: "!",
            badgeLevel: Fluent.Enums.statusLevel.error
        })
    }

    function _selectPath(path) {
        var value = String(path || "")
        if (!switchingEnabled || value === "") return
        if (_pathKey(value) === activePathKey) {
            _setPending(value, false)
            return
        }
        ensurePath(value)
        _setPending(value, true)
        repositorySelected(value)
    }

    function _closePath(path) {
        if (!switchingEnabled || _tabs.length <= 1) return
        var index = _indexForPath(path)
        if (index < 0) return
        var wasActive = _pathKey(path) === activePathKey
        var next = _tabs.slice()
        next.splice(index, 1)
        _tabs = next
        repositoryClosed(String(path))

        if (wasActive && _tabs.length > 0) {
            var nextIndex = Math.min(index, _tabs.length - 1)
            var nextPath = String(_tabs[nextIndex].path || "")
            _closingActivePath = String(path)
            _selectPath(nextPath)
        }
    }

    function _reorderTabs(from, to) {
        if (from < 0 || to < 0 || from >= _tabs.length || to >= _tabs.length || from === to)
            return
        var next = _tabs.slice()
        var moved = next.splice(from, 1)[0]
        next.splice(to, 0, moved)
        _tabs = next
    }

    function _refreshPickerPaths() {
        var recent = gitBridge ? gitBridge.getRecentRepos() : []
        _pickerPaths = repoScanner && repoScanner.mergeWithOpenedRepos
            ? repoScanner.mergeWithOpenedRepos(recent) : recent
    }

    function _openRepositoryPicker() {
        if (!switchingEnabled) return
        _refreshPickerPaths()
        repositorySearchMenu.loading = !!(repoScanner && repoScanner.scanning)
        repositorySearchMenu.prepareForOpen(_pickerPaths)
        repositorySearchMenu.openAtControl(tabBar.addButtonItem)
    }

    // ==================== Size 尺寸 ====================
    implicitHeight: tabHeight
    height: tabHeight

    // ==================== Content 内容 ====================
    Fluent.TabBar {
        id: tabBar
        objectName: "repositoryFluentTabBar"
        anchors.fill: parent
        tabs: root._tabs
        detailsEnabled: true
        tabWidth: Fluent.Enums.controlSize.cardWidth / 2
        minimumTabWidth: Fluent.Enums.controlSize.segmentedMinWidth
        maximumTabWidth: Fluent.Enums.controlSize.cardWidth / 2
        closable: true
        canCloseTab: function(index, tab) { return root._tabs.length > 1 }
        movable: true
        scrollable: true
        showAddButton: true
        interactionEnabled: root.switchingEnabled

        onTabClicked: function(index) {
            if (index < 0 || index >= root._tabs.length) return
            root._selectPath(root._tabs[index].path)
        }

        onTabClosed: function(index) {
            if (index < 0 || index >= root._tabs.length) return
            root._closePath(root._tabs[index].path)
        }

        onTabAddClicked: root._openRepositoryPicker()
        onTabsReordered: function(from, to) { root._reorderTabs(from, to) }
    }

    RepositorySearchMenu {
        id: repositorySearchMenu
        targetControl: tabBar.addButtonItem
        onPathSelected: function(path) { root._selectPath(path) }
    }

    Connections {
        target: root.gitBridge
        enabled: !!root.gitBridge

        function onRepoPathChanged(path) {
            root.ensurePath(path)
            root._setPending(path, false)
            root._closingActivePath = ""
            root._syncCurrentIndex()
            if (root.gitBridge.requestStatus) root.gitBridge.requestStatus()
        }

        function onRepoOpened(ok, value) {
            if (ok) {
                root.ensurePath(value)
                root._setPending(value, false)
                root._syncCurrentIndex()
            } else {
                root._markOpenFailed(value)
                root._syncCurrentIndex()
                if (root._closingActivePath !== "") {
                    root.ensurePath(root._closingActivePath)
                    root._setPending(root._closingActivePath, false)
                    root._closingActivePath = ""
                    root._syncCurrentIndex()
                }
            }
        }

        function onRepoOpenRejected(path, message) {
            root._markOpenFailed(path)
            root._syncCurrentIndex()
            if (root._closingActivePath !== "") {
                root.ensurePath(root._closingActivePath)
                root._setPending(root._closingActivePath, false)
                root._closingActivePath = ""
                root._syncCurrentIndex()
            }
        }

        function onStatusReady(repoPath, count) { root._updateStatus(repoPath, count) }
        function onBranchReady(repoPath, branch) { root._updateBranch(repoPath, branch) }

        function onStatusChanged() {
            if (root.activePath !== "" && root.gitBridge.requestStatus)
                root.gitBridge.requestStatus()
        }
    }

    Connections {
        target: root.repoScanner
        enabled: !!root.repoScanner

        function onScanFinished() {
            if (!repositorySearchMenu.isOpen) return
            root._refreshPickerPaths()
            repositorySearchMenu.loading = false
            repositorySearchMenu.setPaths(root._pickerPaths)
        }
    }

    Shortcut {
        sequence: "Ctrl+Tab"
        enabled: root.switchingEnabled
        onActivated: {
            if (root._tabs.length < 2) return
            var index = root._indexForPath(root.activePath)
            var nextIndex = (index + 1 + root._tabs.length) % root._tabs.length
            root._selectPath(root._tabs[nextIndex].path)
        }
    }

    Shortcut {
        sequence: "Ctrl+Shift+Tab"
        enabled: root.switchingEnabled
        onActivated: {
            if (root._tabs.length < 2) return
            var index = root._indexForPath(root.activePath)
            var nextIndex = (index - 1 + root._tabs.length) % root._tabs.length
            root._selectPath(root._tabs[nextIndex].path)
        }
    }

    Shortcut {
        sequence: "Ctrl+W"
        enabled: root.switchingEnabled
        onActivated: root._closePath(root.activePath)
    }

    Component.onCompleted: {
        if (activePath !== "") {
            ensurePath(activePath)
            _syncCurrentIndex()
        }
    }
}
