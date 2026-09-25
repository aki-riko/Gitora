// RepositoryTabBar - Gitora repository session adapter Gitora 仓库会话适配层
// The visual tab bar is provided by PrismQML; this component owns repository data only.
// 标签视觉由 PrismQML 提供，本组件只负责仓库数据和切换请求。
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Dialogs
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
    // 仓库选择列表按这个宽度省略中间路径,与仓库页保持一致的显示宽度。
    readonly property real _repoPathMenuTextWidth: Fluent.Enums.controlSize.cardWidth
        + Fluent.Enums.spacing.xxxl * 3

    // ==================== Internal Props 内部属性 ====================
    property var _tabs: []
    property var _pickerPaths: []
    property string _closingActivePath: ""
    property string _contextMenuPath: ""
    property var _workspaceItems: []
    property string _workspaceStateRepoPath: ""
    // 会话恢复完成前不回写快照，避免用启动中的空标签覆盖上次会话。
    property bool _sessionRestored: false

    // 仓库选择列表的路径省略用同一套字体度量,保证与仓库页显示一致。
    FontMetrics {
        id: repoPathFontMetrics
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.body
    }

    FontMetrics {
        id: workspaceTextMetrics
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.body
    }

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

    // 把当前标签页快照写回后端；只在结构变化(新增/关闭/排序/切换)后调用，
    // 状态刷新不落盘。写盘本身在后端后台线程执行。
    // activeOverride 传空串表示“用当前 activePath”。
    // 关闭当前活动标签时 activePath 仍指向正在关闭的仓库(它绑定
    // gitBridge.repoPath,要等异步打开完成才更新),此时必须显式传入接管的目标
    // 仓库,否则落盘的 active 不在列表里,重启会回退到第一个标签。
    function _persistSessionWithActive(activeOverride) {
        if (!_sessionRestored || !gitBridge || !gitBridge.saveOpenedRepos) return
        var paths = []
        for (var i = 0; i < _tabs.length; i++) {
            var value = String(_tabs[i].path || "")
            if (value !== "") paths.push(value)
        }
        var override = String(activeOverride || "")
        gitBridge.saveOpenedRepos(paths, override !== "" ? override : activePath)
    }

    function _persistSession() { _persistSessionWithActive("") }

    // 启动时按上次会话快照重建全部标签；活动仓库由后端并行打开。
    function restoreSession(paths, active) {
        var values = []
        var seen = ({})
        for (var i = 0; i < (paths || []).length; i++) {
            var value = String(paths[i] || "")
            var key = _pathKey(value)
            if (value !== "" && !seen[key]) {
                seen[key] = true
                values.push(value)
            }
        }
        if (values.length === 0) {
            _sessionRestored = true
            return
        }

        var next = []
        for (var j = 0; j < values.length; j++) next.push(_newTab(values[j]))
        _tabs = next

        var activePathValue = String(active || "")
        if (activePathValue !== "" && _indexForPath(activePathValue) >= 0)
            _setPending(activePathValue, true)
        _syncCurrentIndex()
        _sessionRestored = true
    }

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
        // 定时轮询的结果可能晚于用户关闭该标签；只更新已存在的标签，
        // 不能让迟到的结果把已关闭的标签重新创建出来。
        if (_indexForPath(path) < 0) return
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
        // 后台补齐的分支结果可能晚于用户关闭该标签；这里只更新已存在的标签，
        // 不能让迟到的结果把已关闭的标签重新创建出来。
        if (_indexForPath(path) < 0) return
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

    function _closeTabsMatching(predicate, fallbackPath) {
        if (!switchingEnabled || _tabs.length <= 1) return false
        var kept = []
        var removed = []
        var activeWillClose = false
        for (var i = 0; i < _tabs.length; i++) {
            var tab = _tabs[i]
            if (predicate(i, tab)) removed.push(tab)
            else kept.push(tab)
        }
        if (removed.length === 0 || kept.length === 0) return false
        for (var j = 0; j < removed.length; j++) {
            if (_pathKey(removed[j].path) === activePathKey) activeWillClose = true
        }
        _tabs = kept
        for (var k = 0; k < removed.length; k++)
            repositoryClosed(String(removed[k].path || ""))
        if (activeWillClose) {
            _closingActivePath = activePath
            _selectPath(fallbackPath)
            // 关掉的是活动标签：activePath 此刻还是那个正在关闭的仓库，
            // 必须按接管的 fallbackPath 落盘。
            _persistSessionWithActive(fallbackPath)
        } else {
            _syncCurrentIndex()
            _persistSession()
        }
        return true
    }

    function _closePath(path) {
        if (!switchingEnabled || _tabs.length <= 1) return false
        var index = _indexForPath(path)
        if (index < 0) return false
        var fallbackIndex = index < _tabs.length - 1 ? index + 1 : index - 1
        var fallbackPath = String(_tabs[fallbackIndex].path || "")
        var pathKey = _pathKey(path)
        return _closeTabsMatching(function(itemIndex, tab) {
            return root._pathKey(tab.path) === pathKey
        }, fallbackPath)
    }

    function _closeOtherTabs(index) {
        if (index < 0 || index >= _tabs.length) return false
        var fallbackPath = String(_tabs[index].path || "")
        return _closeTabsMatching(function(itemIndex, tab) {
            return itemIndex !== index
        }, fallbackPath)
    }

    function _closeTabsToRight(index) {
        if (index < 0 || index >= _tabs.length - 1) return false
        var fallbackPath = String(_tabs[index].path || "")
        return _closeTabsMatching(function(itemIndex, tab) {
            return itemIndex > index
        }, fallbackPath)
    }

    function _contextMenuIndex() {
        return _indexForPath(_contextMenuPath)
    }

    function _workspaceItemsFor(worktrees) {
        var items = []
        var seen = ({})
        for (var i = 0; i < (worktrees || []).length; i++) {
            var worktree = worktrees[i] || {}
            var path = String(worktree.path || "")
            var key = _pathKey(path)
            if (path === "" || seen[key] || worktree.prunable || worktree.bare)
                continue
            seen[key] = true
            items.push({
                text: _repoName(path),
                path: path,
                branch: String(worktree.branch || ""),
                toolTip: path
            })
        }
        return items
    }

    function _workspaceComboIndex(path) {
        var key = _pathKey(path)
        for (var i = 0; i < _workspaceItems.length; i++) {
            if (_pathKey(_workspaceItems[i].path) === key) return i
        }
        return -1
    }

    function _workspaceComboWidth() {
        var maxTextWidth = 0
        for (var i = 0; i < _workspaceItems.length; i++) {
            workspaceTextMetrics.text = String(_workspaceItems[i].text || "")
            maxTextWidth = Math.max(maxTextWidth, workspaceTextMetrics.advanceWidth)
        }
        return Math.max(120, Math.min(190,
            Math.ceil(maxTextWidth) + Fluent.Enums.spacing.xl * 2
                + Fluent.Enums.comboBoxMetrics.arrowAreaWidth))
    }

    function _requestWorktreeState() {
        if (!gitBridge || !gitBridge.requestWorktreeState || activePath === "") {
            _workspaceStateRepoPath = ""
            _workspaceItems = []
            return
        }
        _workspaceStateRepoPath = activePath
        gitBridge.requestWorktreeState()
    }

    function _applyWorkspaceState(repoPath, worktrees) {
        if (!gitBridge || repoPath !== gitBridge.repoPath
                || repoPath !== _workspaceStateRepoPath) return
        _workspaceItems = _workspaceItemsFor(worktrees)
        workspaceSwitcher.currentIndex = _workspaceComboIndex(activePath)
    }

    function _openTabContextMenu(index, position) {
        if (index < 0 || index >= _tabs.length) return
        _contextMenuPath = String(_tabs[index].path || "")
        var popupPosition = position || Qt.point(0, 0)
        repositoryTabContextMenu.exec(
            popupPosition.x, popupPosition.y, tabBar)
    }

    function _reorderTabs(from, to) {
        if (from < 0 || to < 0 || from >= _tabs.length || to >= _tabs.length || from === to)
            return
        var next = _tabs.slice()
        var moved = next.splice(from, 1)[0]
        next.splice(to, 0, moved)
        _tabs = next
        _persistSession()
    }

    function _refreshPickerPaths() {
        var recent = gitBridge ? gitBridge.getRecentRepos() : []
        _pickerPaths = repoScanner && repoScanner.mergeWithOpenedRepos
            ? repoScanner.mergeWithOpenedRepos(recent) : recent
    }

    // 定时轮询全部标签页的徽标(变更数)与分支；活动仓库由后端指纹轮询驱动
    // requestStatus 刷新，后端会自行剔除活动仓库避免重复回传。
    function _pollTabSnapshots() {
        if (!gitBridge || !gitBridge.requestTabSnapshots) return
        var paths = []
        for (var i = 0; i < _tabs.length; i++) {
            var value = String(_tabs[i].path || "")
            if (value !== "") paths.push(value)
        }
        if (paths.length === 0) return
        gitBridge.requestTabSnapshots(paths, activePath)
    }

    function _openRepositoryPicker() {
        if (!switchingEnabled) return
        _refreshPickerPaths()
        repositorySearchMenu.loading = !!(repoScanner && repoScanner.scanning)
        repositorySearchMenu.prepareForOpen(_pickerPaths)
        repositorySearchMenu.openAtControl(tabBar.addButtonItem)
    }

    // “+”入口菜单:原仓库页页头的“打开/初始化”两个按钮统一收敛到这里，
    // 让仓库入口在有/无打开仓库时都只由标签栏承载。
    function _openRepositoryEntryMenu() {
        if (!switchingEnabled) return
        repositorySearchMenu.close()
        repositoryEntryMenu.show(tabBar.addButtonItem)
    }

    // 打开仓库:浏览并选择仓库目录(原“打开”按钮的主操作)。
    function _openRepositoryFolder() {
        openFolderDialog.open()
    }

    // 初始化仓库:先选目录,成功后打开仓库并进入初始化引导(原“初始化”按钮)。
    function _startRepositoryInit() {
        initFolderDialog.open()
    }

    // 初始化引导窗口只在用户选好目录后创建,避免首屏生成第二个 HWND。
    function _ensureInitGuide() {
        if (!initGuideLoader.active) initGuideLoader.active = true
        return initGuideLoader.item
    }

    function _displayRepoPath(path) {
        return repoPathFontMetrics.elidedText(
            String(path || ""), Text.ElideMiddle, _repoPathMenuTextWidth)
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
        tabBarHeight: root.tabHeight
        tabContentVerticalPadding: Fluent.Enums.spacing.m
        tabWidth: Fluent.Enums.controlSize.cardWidth / 2
        minimumTabWidth: Fluent.Enums.controlSize.segmentedMinWidth
        maximumTabWidth: Fluent.Enums.controlSize.cardWidth / 2
        closable: true
        canCloseTab: function(index, tab) { return root._tabs.length > 1 }
        movable: true
        scrollable: true
        showAddButton: true
        contextMenuEnabled: true
        interactionEnabled: root.switchingEnabled

        onTabClicked: function(index) {
            if (index < 0 || index >= root._tabs.length) return
            root._selectPath(root._tabs[index].path)
        }

        onTabClosed: function(index) {
            if (index < 0 || index >= root._tabs.length) return
            root._closePath(root._tabs[index].path)
        }

        onTabAddClicked: root._openRepositoryEntryMenu()
        onTabContextMenuRequested: function(index, position) {
            root._openTabContextMenu(index, position)
        }
        onTabsReordered: function(from, to) { root._reorderTabs(from, to) }
    }

    // 活动标签标题上的透明工作区下拉框，直接切换主工作树与关联 worktree。
    Fluent.ComboBox {
        id: workspaceSwitcher
        objectName: "workspaceSwitcherComboBox"
        parent: root
        x: tabBar.x + tabBar.currentIndex * tabBar.tabWidth
            + Fluent.Enums.spacing.xl + Fluent.Enums.iconSize.s
                + Fluent.Enums.spacing.xs
        y: tabBar.y + Fluent.Enums.spacing.s
        width: root._workspaceComboWidth()
        height: Fluent.Enums.controlSize.inputHeight
        z: Fluent.Enums.zIndex.controlsAbove
        visible: root._workspaceItems.length > 1
            && root.switchingEnabled
        enabled: visible
        style: Fluent.Enums.comboBox.style_transparent
        model: root._workspaceItems
        currentIndex: root._workspaceComboIndex(root.activePath)
        onActivated: function(index) {
            if (index < 0 || index >= root._workspaceItems.length) return
            root._selectPath(root._workspaceItems[index].path)
        }
    }

    Fluent.ContextMenu {
        id: repositoryTabContextMenu
        objectName: "repositoryTabContextMenu"
        autoBindRightClick: false

        Fluent.Action {
            objectName: "repositoryTabCloseAction"
            actionId: "close"
            text: "关闭"
            enabled: root.switchingEnabled && root._tabs.length > 1
                && root._contextMenuIndex() >= 0
            onTriggered: root._closePath(root._contextMenuPath)
        }

        Fluent.Action {
            objectName: "repositoryTabCloseOthersAction"
            actionId: "close_others"
            text: "关闭其他标签页"
            enabled: root.switchingEnabled && root._tabs.length > 1
                && root._contextMenuIndex() >= 0
            onTriggered: root._closeOtherTabs(root._contextMenuIndex())
        }

        Fluent.Action {
            objectName: "repositoryTabCloseRightAction"
            actionId: "close_right"
            text: "关闭右侧标签页"
            enabled: root.switchingEnabled && root._contextMenuIndex() >= 0
                && root._contextMenuIndex() < root._tabs.length - 1
            onTriggered: root._closeTabsToRight(root._contextMenuIndex())
        }
    }

    // 仓库入口菜单:承载原仓库页页头的“打开/初始化”入口。
    Fluent.ContextMenu {
        id: repositoryEntryMenu
        objectName: "repositoryEntryMenu"
        autoBindRightClick: false

        Fluent.Action {
            objectName: "repositoryEntryOpenAction"
            actionId: "open_folder"
            text: "打开仓库…"
            icon: Fluent.Enums.icon.folder
            onTriggered: root._openRepositoryFolder()
        }

        Fluent.Action {
            objectName: "repositoryEntryRecentAction"
            actionId: "open_recent"
            text: "最近仓库…"
            icon: Fluent.Enums.icon.history
            onTriggered: root._openRepositoryPicker()
        }

        Fluent.Action {
            objectName: "repositoryEntryInitAction"
            actionId: "init_repo"
            text: "初始化仓库…"
            icon: Fluent.Enums.icon.add
            onTriggered: root._startRepositoryInit()
        }
    }

    RepositorySearchMenu {
        id: repositorySearchMenu
        targetControl: tabBar.addButtonItem
        pathFormatter: root._displayRepoPath
        onPathSelected: function(path) { root._selectPath(path) }
    }

    // 打开仓库:选择已有仓库目录。
    FolderDialog {
        id: openFolderDialog
        title: "选择 Git 仓库目录"
        onAccepted: {
            if (!root.gitBridge) return
            var path = selectedFolder.toString().replace(/^file:\/\/\//, "")
            if (path !== "") root.gitBridge.openRepoAsync(path)
        }
    }

    // 初始化仓库:先选目录,再走引导。
    FolderDialog {
        id: initFolderDialog
        title: "选择要初始化的目录"
        onAccepted: {
            if (!root.gitBridge) return
            var path = selectedFolder.toString().replace(/^file:\/\/\//, "")
            var task = root.gitBridge.initRepo(path)
            task.succeeded.connect(function(result) {
                if (!result || !result[0]) return
                root.gitBridge.openRepoAsync(path)
                var guide = root._ensureInitGuide()
                if (!guide) return
                guide.repoPath = path
                guide.currentIndex = 0
                guide.show()
            })
        }
    }

    // 初始化引导窗口只在用户完成目录选择后创建,避免首屏生成第二个 HWND。
    Loader {
        id: initGuideLoader
        active: false
        sourceComponent: Component {
            InitRepoGuide {
                onCompleted: function(p) {
                    // 引导里可能写入用户名/邮箱或新增远程:让后端重发当前仓库状态,
                    // 仓库页按既有 statusChanged/statusReady 链路刷新,不再反向依赖页面。
                    if (root.gitBridge && root.gitBridge.requestStatus)
                        root.gitBridge.requestStatus()
                }
            }
        }
    }

    Connections {
        target: root.gitBridge
        enabled: !!root.gitBridge

        function onOpenedReposRestored(paths, active) {
            root.restoreSession(paths, active)
            // 会话恢复后立即拉一轮标签快照，不必等第一个轮询周期。
            Qt.callLater(root._pollTabSnapshots)
        }

        function onRepoPathChanged(path) {
            root._workspaceItems = []
            root._workspaceStateRepoPath = String(path || "")
            root.ensurePath(path)
            root._setPending(path, false)
            root._closingActivePath = ""
            root._syncCurrentIndex()
            root._persistSession()
            if (root.gitBridge.requestStatus) root.gitBridge.requestStatus()
            root._requestWorktreeState()
        }

        function onRepoOpened(ok, value) {
            if (ok) {
                root.ensurePath(value)
                root._setPending(value, false)
                root._syncCurrentIndex()
                root._persistSession()
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
            root._requestWorktreeState()
        }

        function onWorktreeStateReady(repoPath, worktrees) {
            root._applyWorkspaceState(repoPath, worktrees)
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

    // 定时轮询打开页面的徽标与分支；Git 操作忙时切换被禁用，轮询同步暂停。
    Timer {
        id: tabSnapshotPollTimer
        interval: (root.gitBridge && root.gitBridge.tabPollIntervalMs > 0)
            ? root.gitBridge.tabPollIntervalMs : 1000
        repeat: true
        running: root.switchingEnabled && !!root.gitBridge
            && root.activePath !== "" && root.tabCount > 0
        onTriggered: root._pollTabSnapshots()
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
            _requestWorktreeState()
        }
    }
}
