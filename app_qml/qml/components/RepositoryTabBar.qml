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
    // 下拉框相对标签栏的落点；由 _syncWorkspaceGeometry 按标签委托里标题
    // 文字的真实锚点写入，尺寸则由标题文本自身度量决定(见 workspaceSwitcher)。
    property real _workspaceX: 0
    property real _workspaceY: 0
    // 标题文字的可用宽度上限；-1 表示不限制。超长仓库名按原标签行为省略收尾，
    // 不允许下拉框溢出到相邻标签上。
    property real _workspaceTitleMaxWidth: -1
    // 引擎自带的箭头固定距控件右边缘 spacing.l，会撑出多余内边距，只隐藏一次。
    property bool _engineChevronHidden: false
    // 会话恢复完成前不回写快照，避免用启动中的空标签覆盖上次会话。
    property bool _sessionRestored: false

    // 仓库选择列表的路径省略用同一套字体度量,保证与仓库页显示一致。
    FontMetrics {
        id: repoPathFontMetrics
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
            workspaceTitle: _repoName(value),
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
        var current = _tabs[index] || {}
        var patch = changes || {}
        var dirty = false
        for (var key in patch) {
            if (current[key] !== patch[key]) {
                dirty = true
                break
            }
        }
        // 值没变就不要换数组：标签栏按数组身份刷新，轮询回来的同值快照
        // 每次都换一份数组会带来无谓的重排。
        if (!dirty) return
        var next = _tabs.slice()
        next[index] = Object.assign({}, current, patch)
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

    // 工作区下拉框的切换语义：把当前标签就地换成目标工作区，标签数量与位置都
    // 不变；只有打开仓库(点击“+”、最近仓库列表)才在末尾追加新标签。
    function _switchActiveTabWorkspace(path) {
        var value = String(path || "")
        if (!switchingEnabled || value === "") return
        if (_pathKey(value) === activePathKey) {
            _setPending(value, false)
            return
        }
        // 目标工作区已经独立成标签时直接激活那个标签，避免同一路径出现两份。
        if (_indexForPath(value) >= 0) {
            _selectPath(value)
            return
        }
        var index = _indexForPath(activePath)
        if (index < 0) {
            // 活动仓库当前没有独立标签(例如会话恢复中)：退化回追加语义，
            // 否则这次切换没有任何标签可以承载目标工作区。
            _selectPath(value)
            return
        }
        var replacing = _newTab(value)
        // 工作区下拉框正显示在同一位置：标题必须留空，否则会与下拉框重叠成
        // “文字 + 下拉框”同时出现。副标题同步进入“打开中…”，一次赋值到位，
        // 避免分几次替换数组造成标签内容连续跳变。
        if (_workspaceItems.length > 1) replacing.title = ""
        replacing.pending = true
        replacing.subtitle = "打开中…"
        var next = _tabs.slice()
        next[index] = replacing
        _tabs = next
        // 就地替换：标签索引不变，因此不调用 _syncCurrentIndex()——它按旧的
        // activePath 查找会失败，而 currentIndex 本来就指向这个标签。
        // 标签内容变了(宽度也不同)，等新委托落地后再对齐一次下拉框几何。
        Qt.callLater(_syncWorkspaceGeometry)
        repositorySelected(value)
    }

    function _closeTabsMatching(predicate, fallbackPath) {
        if (!switchingEnabled || _tabs.length <= 1) return false
        var kept = []
        var removed = []
        var activeWillClose = false
        // 活动标签以标签栏当前索引为准。活动仓库此刻可能没有独立标签(就地切换
        // 尚未完成或打开失败时 activePath 会与标签列表脱节)，只看 activePath
        // 会把这种情形判成“关掉的不是活动标签”，从而把脱节的 active 落盘。
        var currentIndex = tabBar ? tabBar.currentIndex : -1
        var currentPathKey = currentIndex >= 0 && currentIndex < _tabs.length
            ? _pathKey(String(_tabs[currentIndex].path || "")) : ""
        for (var i = 0; i < _tabs.length; i++) {
            var tab = _tabs[i]
            if (predicate(i, tab)) removed.push(tab)
            else kept.push(tab)
        }
        if (removed.length === 0 || kept.length === 0) return false
        for (var j = 0; j < removed.length; j++) {
            var removedKey = _pathKey(removed[j].path)
            if (removedKey === activePathKey
                    || (currentPathKey !== "" && removedKey === currentPathKey))
                activeWillClose = true
        }
        _tabs = kept
        for (var k = 0; k < removed.length; k++)
            repositoryClosed(String(removed[k].path || ""))
        if (activeWillClose) {
            // _closingActivePath 用于打开失败后恢复被关闭的标签：就地切换期间
            // activePath 可能已脱节，此时以当前标签自己的路径为准。
            var closingPath = activePath
            if (_pathKey(activePath) !== currentPathKey) {
                for (var m = 0; m < removed.length; m++) {
                    if (_pathKey(removed[m].path) === currentPathKey) {
                        closingPath = String(removed[m].path || "")
                        break
                    }
                }
            }
            _closingActivePath = closingPath
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

    function _syncWorkspaceTabTitle() {
        var next = _tabs.slice()
        var changed = false
        var hideActiveTitle = _workspaceItems.length > 1
        for (var i = 0; i < next.length; i++) {
            var tab = next[i] || {}
            var title = hideActiveTitle && _pathKey(tab.path) === activePathKey
                ? "" : String(tab.workspaceTitle || tab.title || "")
            if (String(tab.title || "") !== title) {
                next[i] = Object.assign({}, tab, {title: title})
                changed = true
            }
        }
        if (changed) {
            _tabs = next
            // 整表替换会让标签委托重建，等新委托落地后再按真实锚点对齐一次。
            Qt.callLater(_syncWorkspaceGeometry)
        }
    }

    // 引擎 TabBar 没有导出内部 Flickable/Row/委托，只能用结构特征逐层定位。
    // 定位失败时返回 null，调用方走退化路径，绝不长期停留在猜测坐标上。

    // 标签栏里的横向 Flickable(标签滚动容器)。
    function _tabFlickable() {
        var kids = tabBar ? tabBar.children : null
        for (var i = 0; kids && i < kids.length; i++) {
            var kid = kids[i]
            if (kid && typeof kid.contentX === "number"
                    && typeof kid.contentWidth === "number")
                return kid
        }
        return null
    }

    // 承载标签委托的 Row(标签条目容器)。
    function _tabRow() {
        var flick = _tabFlickable()
        var content = flick ? flick.contentItem : null
        if (!content) return null
        var rows = content.children || []
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i]
            if (!row || typeof row.spacing !== "number") continue
            var items = row.children || []
            for (var j = 0; j < items.length; j++) {
                if (items[j] && typeof items[j].index === "number") return row
            }
        }
        return null
    }

    // 当前活动标签的委托；mapToItem 会连同标签栏滚动偏移一起换算。
    function _workspaceTabItem() {
        var index = tabBar ? tabBar.currentIndex : -1
        if (index < 0) return null
        var row = _tabRow()
        var items = row ? (row.children || []) : []
        for (var i = 0; i < items.length; i++) {
            if (items[i] && items[i].index === index) return items[i]
        }
        return null
    }

    // 活动标签标题文字的真实锚点(相对标签委托)：文字左边界与文字行垂直中心。
    // 直接读取引擎委托里 detailContent/detailTitleRow/标题 Label 的布局结果，
    // 使下拉框主体与标题文字逐像素对齐，而不是靠固定偏移猜测。
    function _workspaceTitleAnchor(item) {
        if (!item) return null
        var kids = item.children || []
        var detail = null
        for (var i = 0; i < kids.length; i++) {
            if (kids[i] && kids[i].objectName === "tabItemDetailContent") {
                detail = kids[i]
                break
            }
        }
        if (!detail || !detail.visible) return null
        var rows = detail.children || []
        var titleRow = null
        for (var j = 0; j < rows.length; j++) {
            var candidate = rows[j]
            if (candidate && typeof candidate.spacing === "number"
                    && candidate.height > 0) {
                titleRow = candidate
                break
            }
        }
        if (!titleRow) return null
        var leaves = titleRow.children || []
        var titleLabel = null
        for (var k = 0; k < leaves.length; k++) {
            var leaf = leaves[k]
            if (leaf && leaf.visible && typeof leaf.text === "string") {
                titleLabel = leaf
                break
            }
        }
        if (!titleLabel) return null
        return {
            left: detail.x + titleRow.x + titleLabel.x,
            centerY: detail.y + titleRow.y + titleLabel.y + titleLabel.height / 2,
            // 标题为空时该 Label 会撑满标题行可用宽度，正好是标题区可占的上限。
            availableWidth: titleLabel.width
        }
    }

    // 箭头区宽度(文本到箭头的间距 + 箭头本身)。下拉框主体与箭头都贴边排布后，
    // 这段宽度要从标题可用宽度里扣除，避免挤到 badge 或标签外。
    function _workspaceArrowArea() {
        return Fluent.Enums.spacing.m + Fluent.Enums.controlSize.checkIconSize
    }

    // 控件矩形相对“文本 + 箭头”在左右各留的极小呼吸位，避免文字/箭头紧贴边框。
    function _workspaceEdgePadding() {
        return Fluent.Enums.spacing.xxs
    }

    // 引擎箭头固定在距控件右边缘 spacing.l 处；透明样式的高亮背景会把这段空白
    // 一起画出来，形成左右各一段多余内边距。隐藏它，改由本组件在控件右边缘
    // 自绘同款箭头，使背景正好包住“文本 + 箭头”。
    function _hideEngineChevron() {
        if (_engineChevronHidden) return
        var kids = workspaceSwitcher ? workspaceSwitcher.children : null
        for (var i = 0; kids && i < kids.length; i++) {
            var content = kids[i]
            if (!content || typeof content.comboControl === "undefined") continue
            var inner = content.children || []
            for (var j = 0; j < inner.length; j++) {
                var child = inner[j]
                if (child && typeof child.direction === "string"
                        && typeof child.isOpen === "boolean") {
                    child.visible = false
                    _engineChevronHidden = true
                    return
                }
            }
        }
    }

    function _syncWorkspaceGeometry() {
        _hideEngineChevron()
        var item = _workspaceTabItem()
        var anchor = _workspaceTitleAnchor(item)
        if (!item || !anchor) {
            // 标签委托尚未建立(首帧或模型重建中)：先落在标签栏内容区左上，
            // 委托可用后会在同一拍或下一次同步里被真实锚点覆盖。
            _workspaceX = tabBar.x + Fluent.Enums.spacing.xs
            _workspaceY = tabBar.y + Math.max(
                0, (tabHeight - workspaceSwitcher.height) / 2)
            _workspaceTitleMaxWidth = -1
            return
        }
        _workspaceTitleMaxWidth = Math.max(
            0, anchor.availableWidth - _workspaceArrowArea()
                - _workspaceEdgePadding() * 2)
        var origin = item.mapToItem(root, anchor.left, anchor.centerY)
        // 控件矩形紧贴可见区域：左右各留 _workspaceEdgePadding 呼吸位，
        // 左边缘外推同样的距离后，内部文字左边界仍与标题文字左边界重合。
        _workspaceX = origin.x - _workspaceEdgePadding()
        _workspaceY = origin.y - workspaceSwitcher.height / 2
    }

    function _requestWorktreeState() {
        if (!gitBridge || !gitBridge.requestWorktreeState || activePath === "") {
            _workspaceStateRepoPath = ""
            _workspaceItems = []
            _syncWorkspaceTabTitle()
            return
        }
        _workspaceStateRepoPath = activePath
        gitBridge.requestWorktreeState()
    }

    // 工作区列表内容比较：列表没变就不换数组，避免下拉框按新 model 重新布局。
    function _sameWorkspaceItems(left, right) {
        var a = left || []
        var b = right || []
        if (a.length !== b.length) return false
        for (var i = 0; i < a.length; i++) {
            if (String(a[i].path || "") !== String(b[i].path || "")
                    || String(a[i].text || "") !== String(b[i].text || "")
                    || String(a[i].branch || "") !== String(b[i].branch || ""))
                return false
        }
        return true
    }

    function _applyWorkspaceState(repoPath, worktrees) {
        if (!gitBridge || repoPath !== gitBridge.repoPath
                || repoPath !== _workspaceStateRepoPath) return
        var items = _workspaceItemsFor(worktrees)
        if (!_sameWorkspaceItems(items, _workspaceItems))
            _workspaceItems = items
        workspaceSwitcher.currentIndex = _workspaceComboIndex(activePath)
        _syncWorkspaceTabTitle()
        _syncWorkspaceGeometry()
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
    // 控件矩形只比“标题文字 + 箭头”大出左右各 _workspaceEdgePadding 的呼吸位：
    // 宽 = 呼吸位 + 文字 + 箭头区 + 呼吸位，高 = 文字行高；左边缘外推同一位移，
    // 保证内部文字左边界与标签标题文字左边界重合。
    // 用 ComboBoxDefault 而不是 ComboBox：ComboBox 是 ComboBoxEntry 的门面，
    // 不转发 useDefaultContent，无法把引擎默认的 body 字号文本换成标题同款文本。
    Fluent.ComboBoxDefault {
        id: workspaceSwitcher
        objectName: "workspaceSwitcherComboBox"
        parent: root
        x: root._workspaceX
        y: root._workspaceY
        width: root._workspaceEdgePadding() + workspaceTitleText.width
            + root._workspaceArrowArea() + root._workspaceEdgePadding()
        height: workspaceTitleText.implicitHeight
        z: Fluent.Enums.zIndex.controlsAbove
        visible: root._workspaceItems.length > 1
            && root.switchingEnabled
        enabled: visible
        style: Fluent.Enums.comboBox.style_transparent
        // 引擎默认内容用 body 字号与主文本色，与标签标题(caption/加粗/前景色)
        // 不一致，会在同一行里显出字号与颜色差；这里改为自行提供与标题同款的
        // 文本与箭头，只借用下拉框的透明样式与弹层行为。
        useDefaultContent: false
        model: root._workspaceItems
        currentIndex: root._workspaceComboIndex(root.activePath)
        onActivated: function(index) {
            if (index < 0 || index >= root._workspaceItems.length) return
            // 工作区之间就地切换：当前标签换成目标工作区，不追加新标签。
            root._switchActiveTabWorkspace(root._workspaceItems[index].path)
        }

        Fluent.Label {
            id: workspaceTitleText
            anchors.left: parent.left
            anchors.leftMargin: root._workspaceEdgePadding()
            anchors.verticalCenter: parent.verticalCenter
            width: root._workspaceTitleMaxWidth > 0
                ? Math.min(implicitWidth, root._workspaceTitleMaxWidth)
                : implicitWidth
            type: Fluent.Enums.label.type_caption
            color: Fluent.Enums.foregroundColor
            font.bold: true
            text: workspaceSwitcher.currentText
            wrapMode: Text.NoWrap
            // 与原标签标题一致：超长仓库名省略收尾，不溢出到相邻标签。
            elide: Text.ElideRight
        }

        // 引擎箭头被隐藏，这里在右边缘自绘同款箭头，贴合控件边界。
        Fluent.ChevronIcon {
            id: workspaceChevron
            anchors.right: parent.right
            anchors.rightMargin: root._workspaceEdgePadding()
            anchors.verticalCenter: parent.verticalCenter
            animated: true
            isOpen: workspaceSwitcher.isOpen
            color: Fluent.Enums.textColor.secondary
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
            // 就地切换工作区时目标本来就在当前 worktree 列表里，列表继续有效；
            // 一旦清空，下拉框会先消失、标题文字闪回，等列表回来再切回下拉框，
            // 在同一位置来回跳变，看起来就是标签内容疯狂闪烁。
            if (root._workspaceComboIndex(path) < 0) root._workspaceItems = []
            root._workspaceStateRepoPath = String(path || "")
            root._syncWorkspaceTabTitle()
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

    // 标签栏横向滚动时，标题锚点在标签栏坐标系里会整体平移；直接挂在滚动位置
    // 变化上同步，避免用高频轮询去追赶滚动。
    Connections {
        target: root._tabFlickable()

        function onContentXChanged() { root._syncWorkspaceGeometry() }
    }

    // 切换标签页后，下拉框要跟到新的活动标签上。
    Connections {
        target: tabBar

        function onCurrentIndexChanged() { root._syncWorkspaceGeometry() }
    }

    // 标签委托重建、标签高度变化、窗口缩放等结构性变化后的兜底同步；
    // 滚动跟随由上面的 contentX 连接负责，不再依赖这个周期。
    Timer {
        id: workspaceLayoutTimer
        interval: 250
        repeat: true
        running: root.switchingEnabled && workspaceSwitcher.visible
        onTriggered: root._syncWorkspaceGeometry()
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
            _syncWorkspaceGeometry()
        }
    }
}
