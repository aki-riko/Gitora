// 已打开仓库的全局标签栏。
// 标签栏位于 PrismQML 导航窗口的内容层上方，不替换左侧封装导航。
pragma ComponentBehavior: Bound
import QtQuick
import PrismQML as Fluent

Item {
    id: root

    property var gitBridge: null
    property var repoScanner: null
    property bool switchingEnabled: true
    property int tabHeight: Fluent.Enums.controlSize.tableHeaderHeight
    property var _pickerPaths: []
    property string _closingActivePath: ""

    readonly property string activePath: gitBridge ? (gitBridge.repoPath || "") : ""
    readonly property string activePathKey: _pathKey(activePath)
    readonly property int tabCount: tabModel.count

    signal repositorySelected(string path)
    signal repositoryClosed(string path)

    implicitHeight: tabHeight
    height: tabHeight

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
        for (var i = 0; i < tabModel.count; i++) {
            if (_pathKey(tabModel.get(i).path) === key) return i
        }
        return -1
    }

    function _appendPath(path) {
        var value = String(path || "")
        if (value === "" || _indexForPath(value) >= 0)
            return false
        tabModel.append({
            path: value,
            name: _repoName(value),
            branch: "",
            changeCount: -1,
            repoState: "unknown",
            pending: false
        })
        return true
    }

    function ensurePath(path) {
        _appendPath(path)
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

        tabModel.clear()
        for (var k = 0; k < values.length; k++) _appendPath(values[k])
    }

    function _setPending(path, pending) {
        var index = _indexForPath(path)
        if (index >= 0) tabModel.setProperty(index, "pending", pending)
    }

    function _selectPath(path) {
        var value = String(path || "")
        if (!switchingEnabled || value === "" || _pathKey(value) === activePathKey) {
            _setPending(value, false)
            return
        }
        ensurePath(value)
        _setPending(value, true)
        repositorySelected(value)
    }

    function _updateStatus(path, count) {
        var index = _indexForPath(path)
        if (index < 0) {
            ensurePath(path)
            index = _indexForPath(path)
        }
        if (index < 0) return
        var normalizedCount = Math.max(0, Number(count) || 0)
        tabModel.setProperty(index, "changeCount", normalizedCount)
        tabModel.setProperty(index, "repoState", normalizedCount > 0 ? "dirty" : "clean")
    }

    function _updateBranch(path, branch) {
        var index = _indexForPath(path)
        if (index < 0) {
            ensurePath(path)
            index = _indexForPath(path)
        }
        if (index >= 0) tabModel.setProperty(index, "branch", String(branch || ""))
    }

    function _markOpenFailed(path) {
        var index = _indexForPath(path)
        if (index < 0) return
        tabModel.setProperty(index, "pending", false)
        tabModel.setProperty(index, "repoState", "error")
        tabModel.setProperty(index, "branch", "无法打开")
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
        repositorySearchMenu.openAtControl(addButton)
    }

    function _closePath(path) {
        if (!switchingEnabled || tabModel.count <= 1) return
        var index = _indexForPath(path)
        if (index < 0) return
        var wasActive = _pathKey(path) === activePathKey
        tabModel.remove(index)
        repositoryClosed(String(path))

        if (wasActive && tabModel.count > 0) {
            var nextIndex = Math.min(index, tabModel.count - 1)
            var nextPath = String(tabModel.get(nextIndex).path || "")
            _closingActivePath = String(path)
            _selectPath(nextPath)
        }
    }

    function _selectNextTab(direction) {
        if (!switchingEnabled || tabModel.count < 2) return
        var currentIndex = _indexForPath(activePath)
        if (currentIndex < 0) currentIndex = 0
        var nextIndex = (currentIndex + direction + tabModel.count) % tabModel.count
        var nextPath = String(tabModel.get(nextIndex).path || "")
        _selectPath(nextPath)
    }

    ListModel {
        id: tabModel
    }

    Rectangle {
        anchors.fill: parent
        color: Fluent.Enums.stateColor.cardDefaultBg
        border.width: Fluent.Enums.surfaceBorderWidth(Fluent.Enums.border.thin)
        border.color: Fluent.Enums.stateColor.navDivider
    }

    ListView {
        id: tabList
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: addButton.left
        anchors.rightMargin: Fluent.Enums.spacing.xs
        orientation: ListView.Horizontal
        model: tabModel
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        interactive: contentWidth > width
        spacing: 0

        delegate: Item {
            id: tabDelegate
            required property string path
            required property string name
            required property string branch
            required property int changeCount
            required property string repoState
            required property bool pending
            readonly property bool isActive: root._pathKey(tabDelegate.path) === root.activePathKey
            readonly property bool isPending: tabDelegate.pending
            width: Math.max(
                Fluent.Enums.controlSize.cardWidth / 2,
                Math.min(
                    Fluent.Enums.controlSize.cardWidth,
                    Math.floor(root.width / Math.max(1, Math.min(tabModel.count, 4)))
                )
            )
            height: root.height

            Rectangle {
                anchors.fill: parent
                color: tabDelegate.isActive
                    ? Fluent.Enums.cardColor
                    : (tabHover.containsMouse ? Fluent.Enums.stateColor.hover : Fluent.Enums.transparent)
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: Fluent.Enums.surfaceBorderWidth(Fluent.Enums.border.normal)
                color: Fluent.Enums.accentColor
                visible: tabDelegate.isActive
            }

            Rectangle {
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                width: Fluent.Enums.surfaceBorderWidth(Fluent.Enums.border.thin)
                color: Fluent.Enums.stateColor.navDivider
            }

            Fluent.Icon {
                id: tabIcon
                anchors.left: parent.left
                anchors.leftMargin: Fluent.Enums.spacing.m
                anchors.verticalCenter: parent.verticalCenter
                icon: Fluent.Enums.icon.folder
                iconSize: Fluent.Enums.iconSize.s
                color: tabDelegate.isActive
                    ? Fluent.Enums.accentColor : Fluent.Enums.textColor.secondary
            }

            Column {
                anchors.left: tabIcon.right
                anchors.leftMargin: Fluent.Enums.spacing.s
                anchors.right: closeButton.left
                anchors.rightMargin: Fluent.Enums.spacing.xs
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1

                Text {
                    width: parent.width
                    text: tabDelegate.name || root._repoName(tabDelegate.path)
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    font.bold: tabDelegate.isActive
                    elide: Text.ElideRight
                    maximumLineCount: 1
                }

                Row {
                    width: parent.width
                    spacing: Fluent.Enums.spacing.xs

                    Text {
                        width: Math.max(0, parent.width - statusLabel.width - Fluent.Enums.spacing.xs)
                        text: tabDelegate.isPending
                            ? "打开中…"
                            : (tabDelegate.branch || "未读取分支")
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                        elide: Text.ElideRight
                        maximumLineCount: 1
                    }

                    Text {
                        id: statusLabel
                        text: tabDelegate.isPending || tabDelegate.changeCount < 0
                            ? (tabDelegate.repoState === "error" ? "!" : "")
                            : (tabDelegate.repoState === "clean"
                                ? "干净" : String(tabDelegate.changeCount))
                        color: tabDelegate.repoState === "error"
                            ? Fluent.Enums.statusLevel.errorColor
                            : (tabDelegate.repoState === "dirty"
                                ? Fluent.Enums.statusLevel.warningColor
                                : Fluent.Enums.textColor.tertiary)
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                        visible: text !== ""
                    }
                }
            }

            Fluent.CloseButton {
                id: closeButton
                anchors.right: parent.right
                anchors.rightMargin: Fluent.Enums.spacing.xs
                anchors.verticalCenter: parent.verticalCenter
                size: Fluent.Enums.controlSize.closeButtonSize
                iconSizeValue: Fluent.Enums.iconSize.xs
                enabled: root.switchingEnabled && tabModel.count > 1
                opacity: enabled
                    ? Fluent.Enums.opacityLevel.visible : Fluent.Enums.opacityLevel.disabled
                Accessible.name: "关闭 " + (tabDelegate.name
                    || root._repoName(tabDelegate.path))
                onClicked: root._closePath(tabDelegate.path)
            }

            MouseArea {
                id: tabHover
                anchors.fill: parent
                anchors.rightMargin: closeButton.width + Fluent.Enums.spacing.xs
                hoverEnabled: true
                enabled: root.switchingEnabled
                cursorShape: Qt.PointingHandCursor
                onClicked: root._selectPath(tabDelegate.path)
            }
        }
    }

    Fluent.Button {
        id: addButton
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: root.height
        icon: Fluent.Enums.icon.add
        style: Fluent.Enums.button.style_transparent
        enabled: root.switchingEnabled
        toolTipText: "打开仓库"
        onClicked: root._openRepositoryPicker()
    }

    Rectangle {
        anchors.right: addButton.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Fluent.Enums.surfaceBorderWidth(Fluent.Enums.border.thin)
        color: Fluent.Enums.stateColor.navDivider
    }

    RepositorySearchMenu {
        id: repositorySearchMenu
        targetControl: addButton
        onPathSelected: function(path) {
            root._selectPath(path)
        }
    }

    Connections {
        target: root.gitBridge
        enabled: !!root.gitBridge

        function onRepoPathChanged(path) {
            root.ensurePath(path)
            root._setPending(path, false)
            root._closingActivePath = ""
            root.gitBridge.requestStatus()
        }

        function onRepoOpened(ok, value) {
            if (ok) {
                root.ensurePath(value)
                root._setPending(value, false)
            } else {
                root._markOpenFailed(value)
                if (root._closingActivePath !== "") {
                    root.ensurePath(root._closingActivePath)
                    root._setPending(root._closingActivePath, false)
                    root._closingActivePath = ""
                }
            }
        }

        function onRepoOpenRejected(path, message) {
            root._markOpenFailed(path)
        }

        function onStatusReady(repoPath, count) {
            root._updateStatus(repoPath, count)
        }

        function onBranchReady(repoPath, branch) {
            root._updateBranch(repoPath, branch)
        }

        function onStatusChanged() {
            if (root.activePath !== "") root.gitBridge.requestStatus()
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
        onActivated: root._selectNextTab(1)
    }

    Shortcut {
        sequence: "Ctrl+Shift+Tab"
        onActivated: root._selectNextTab(-1)
    }

    Shortcut {
        sequence: "Ctrl+W"
        onActivated: {
            if (root.switchingEnabled && root.activePath !== "")
                root._closePath(root.activePath)
        }
    }

    Component.onCompleted: {
        if (activePath !== "") ensurePath(activePath)
    }
}
