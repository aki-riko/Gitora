// 仓库视图(阶段 2:完整迁移 repo_interface.py)
// 布局:Header(仓库信息+操作) + SplitPane(左:文件列表+提交面板 / 右:Diff)
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs

import PrismQML as Fluent
import "../components"

Item {
    id: root

    // 当前选中的文件(用于 diff)
    property string selectedPath: ""
    property bool selectedStaged: false
    property bool _statusRequesting: false
    property bool _reloadPending: false
    property string _statusRequestRepoPath: ""
    property bool _changeListActive: false

    // ==================== 数据加载 ====================
    function _resetRepoUi() {
        branchLabel.text = ""
        changeModel.clear()
        root._changeListActive = false
        root.selectedPath = ""
        root.selectedStaged = false
        diffView.text = ""
        if (changeListLoader.item && changeListLoader.item.scrollToTop)
            changeListLoader.item.scrollToTop()
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) {
            root._statusRequesting = false
            root._reloadPending = false
            root._statusRequestRepoPath = ""
            root._resetRepoUi()
            return
        }
        if (root._statusRequesting) {
            root._reloadPending = true
            return
        }
        // 后台获取,结果经 statusReady/branchReady 回填,不阻塞主线程
        root._statusRequesting = true
        root._reloadPending = false
        root._statusRequestRepoPath = GitBridge.repoPath
        GitBridge.requestStatus()
    }

    // 修补上次提交:用输入框内容重写 HEAD 的提交消息(git commit --amend)
    function doAmend() {
        var res = GitBridge.amendCommit(commitInput.text)
        if (res[0]) {
            commitInput.text = ""
            Fluent.NotificationManager.toast.success(root, "已修补提交", res[1] || "")
            root.reload()
        } else {
            Fluent.NotificationManager.toast.error(root, "修补失败", res[1] || "")
        }
    }

    function _finishStatusRequest(repoPath) {
        if (repoPath !== root._statusRequestRepoPath) return
        root._statusRequesting = false
        root._statusRequestRepoPath = ""
        if (root._reloadPending) {
            root._reloadPending = false
            Qt.callLater(function() { root.reload() })
        }
    }

    function showDiff(path, staged) {
        root.selectedPath = path
        root.selectedStaged = staged
        diffView.text = ""
        if (GitBridge && path) {
            diffView.text = "加载中..."
            GitBridge.requestDiff(path, staged)  // 异步,结果经 diffReady 回传
        }
    }

    function _defaultRemoteName() {
        var remotes = GitBridge ? GitBridge.getRemoteInfo() : []
        if (!remotes || remotes.length === 0) return "origin"
        for (var i = 0; i < remotes.length; i++) {
            if (remotes[i].name === "origin") return "origin"
        }
        return remotes[0].name || "origin"
    }

    function _defaultBranchName() {
        var branch = GitBridge ? GitBridge.getCurrentBranch() : ""
        return branch === "HEAD" ? "" : branch
    }

    // diff 纯文本 -> 按行着色的 HTML(+绿/-红/@@蓝/文件头灰)
    function _diffToHtml(raw) {
        if (!raw) return ""
        var isDark = (typeof ThemeManager !== "undefined") && ThemeManager.isDark
        var cAdd = isDark ? "#4ec97a" : "#1a7f37"
        var cDel = isDark ? "#f47067" : "#cf222e"
        var cHunk = isDark ? "#6cb6ff" : "#0969da"
        var cMeta = isDark ? "#8b949e" : "#8a8a8a"
        var cNormal = isDark ? "#d0d0d0" : "#1f1f1f"
        var lines = raw.split("\n")
        var out = []
        for (var i = 0; i < lines.length; i++) {
            var ln = lines[i]
            var esc = ln.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            if (esc === "") esc = "&nbsp;"
            var color = cNormal
            if (ln.indexOf("+++") === 0 || ln.indexOf("---") === 0 || ln.indexOf("diff ") === 0 || ln.indexOf("index ") === 0)
                color = cMeta
            else if (ln.indexOf("@@") === 0) color = cHunk
            else if (ln.charAt(0) === "+") color = cAdd
            else if (ln.charAt(0) === "-") color = cDel
            out.push('<span style="color:' + color + '">' + esc + '</span>')
        }
        return '<pre style="margin:0;font-family:Consolas,monospace">' + out.join("<br>") + '</pre>'
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onRepoPathChanged(path) {
            root._statusRequesting = false
            root._reloadPending = false
            root._statusRequestRepoPath = ""
            root._resetRepoUi()
            root.reload()
        }
        function onStatusReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return  // 过期/切仓库,丢弃
            changeModel.clear()
            var stillThere = false
            for (var i = 0; i < list.length; i++) {
                changeModel.append(list[i])
                // 同时匹配 path 和 staged:暂存状态变了也算"已变",清空过期 diff
                if (list[i].path === root.selectedPath && list[i].staged === root.selectedStaged)
                    stillThere = true
            }
            root._changeListActive = changeModel.count > 0
            // 选中的文件已不在变更列表或暂存状态已变 → 清空 diff,避免显示过期内容
            if (root.selectedPath !== "" && !stillThere) {
                root.selectedPath = ""
                diffView.text = ""
            }
            root._finishStatusRequest(repoPath)
        }
        function onBranchReady(repoPath, branch) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return
            branchLabel.text = branch
        }
        function onOperationFinished(ok, msg) {
            if (ok)
                root.reload()
        }
        function onDiffReady(repoPath, path, staged, content) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return
            // 仅当结果对应当前选中项时才填充(防快速切换的过期结果覆盖)
            if (path === root.selectedPath && staged === root.selectedStaged)
                diffView.text = root._diffToHtml(content)
        }
        function onRepoOpened(ok, pathOrErr) {
            if (ok) openButton.rebuildList()
            else console.warn("打开仓库失败:", pathOrErr)
        }
    }

    Component.onCompleted: root.reload()

    ListModel { id: changeModel }

    // 外部变化的刷新由后端 GitBridge 统一轮询驱动:检测到指纹变化 → 发 statusChanged,
    // 上方 Connections.onStatusChanged 已接管刷新,故此处不再需要视图自轮询 Timer。

    // ==================== 布局 ====================
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        spacing: Fluent.Enums.spacing.l

        // ---------- Header ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.m

            Text {
                text: "仓库"
                font.pixelSize: Fluent.Enums.typography.displayLarge
                font.bold: true
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
            }
            Text {
                id: branchLabel
                visible: text !== ""
                color: Fluent.Enums.accentColor
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                font.bold: true
            }
            Item { Layout.fillWidth: true }

            Fluent.Button {
                id: openButton
                text: "打开"
                icon: Fluent.Enums.icon.folder
                feature: Fluent.Enums.button.feature_split
                // 主按钮:选目录;下拉:最近仓库 + 后台扫描到的仓库(去重)
                property var pathList: []
                menuItems: {
                    var items = []
                    for (var i = 0; i < pathList.length; i++)
                        items.push({ "text": pathList[i], "icon": Fluent.Enums.icon.folder })
                    if (items.length === 0)
                        items.push({ "text": (RepoScanner && RepoScanner.scanning) ? "正在扫描磁盘..." : "暂无最近仓库", "icon": Fluent.Enums.icon.info })
                    return items
                }
                function rebuildList() {
                    var seen = ({})
                    var merged = []
                    var recent = GitBridge ? GitBridge.getRecentRepos() : []
                    var scanned = (typeof RepoScanner !== "undefined") ? RepoScanner.getResults() : []
                    var all = recent.concat(scanned)
                    for (var i = 0; i < all.length; i++) {
                        var p = all[i]
                        if (!seen[p]) { seen[p] = true; merged.push(p) }
                    }
                    pathList = merged
                }
                Component.onCompleted: rebuildList()
                onClicked: folderDialog.open()
                onMenuItemClicked: function(index, text) {
                    if (index >= 0 && index < pathList.length) {
                        GitBridge.openRepoAsync(pathList[index])
                    }
                }
                // 扫描有新结果时刷新下拉
                Connections {
                    target: typeof RepoScanner !== "undefined" ? RepoScanner : null
                    function onScanFinished(n) { openButton.rebuildList() }
                }
            }
            Fluent.Button { text: "克隆"; icon: Fluent.Enums.icon.cloud; onClicked: cloneDialog.open() }
            Fluent.Button { text: "初始化"; icon: Fluent.Enums.icon.add; onClicked: initFolderDialog.open() }
            // 拉取:主按钮 pull;下拉出变基/抓取/指定同步/远程覆盖本地
            Fluent.Button {
                text: "拉取"
                icon: Fluent.Enums.icon.arrow_download
                feature: Fluent.Enums.button.feature_split
                menuItems: [
                    { "text": "拉取(变基)", "icon": Fluent.Enums.icon.arrow_download },
                    { "text": "抓取(fetch)", "icon": Fluent.Enums.icon.arrow_sync },
                    { "text": "指定拉取", "icon": Fluent.Enums.icon.branch },
                    { "text": "指定变基拉取", "icon": Fluent.Enums.icon.branch },
                    { "text": "指定抓取远程", "icon": Fluent.Enums.icon.arrow_sync },
                    { "text": "远程覆盖本地", "icon": Fluent.Enums.icon.warning }
                ]
                onClicked: GitBridge.pull()
                onMenuItemClicked: function(index, text) {
                    if (index === 0) GitBridge.pullRebase()
                    else if (index === 1) GitBridge.fetch()
                    else if (index === 2) syncDialog.openFor("pull")
                    else if (index === 3) syncDialog.openFor("pullRebase")
                    else if (index === 4) syncDialog.openFor("fetch")
                    else if (index === 5) forceResetToUpstreamDanger.start()
                }
            }
            // 推送:主按钮 push;下拉出指定推送和强制推送(破坏性,走危险确认)
            Fluent.Button {
                text: "推送"
                icon: Fluent.Enums.icon.arrow_upload
                feature: Fluent.Enums.button.feature_split
                menuItems: [
                    { "text": "指定推送", "icon": Fluent.Enums.icon.branch },
                    { "text": "强制推送", "icon": Fluent.Enums.icon.warning },
                    { "text": "指定强制推送", "icon": Fluent.Enums.icon.warning }
                ]
                onClicked: GitBridge.push()
                onMenuItemClicked: function(index, text) {
                    if (index === 0) syncDialog.openFor("push")
                    else if (index === 1) {
                        forcePushDanger._remote = ""
                        forcePushDanger._branch = ""
                        forcePushDanger.start()
                    } else if (index === 2) syncDialog.openFor("pushForce")
                }
            }
        }

        Text {
            id: repoPathLabel
            Layout.fillWidth: true
            text: (GitBridge && GitBridge.repoPath) ? GitBridge.repoPath : "未打开仓库"
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            elide: Text.ElideMiddle
        }

        // ---------- 提交区(横跨全宽) ----------
        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.m
            Fluent.LineEdit {
                id: commitInput
                Layout.fillWidth: true
                placeholderText: "提交信息"
            }
            Fluent.Button {
                text: "提交"
                style: Fluent.Enums.button.style_primary
                enabled: commitInput.text.length > 0
                feature: Fluent.Enums.button.feature_split
                // 下拉:修补上次提交(commit --amend),用输入框内容作为新提交消息
                menuItems: [
                    { "text": "修补上次提交", "icon": Fluent.Enums.icon.edit }
                ]
                onClicked: {
                    var res = GitBridge.commit(commitInput.text)
                    if (res[0]) {
                        commitInput.text = ""
                        Fluent.NotificationManager.toast.success(root, "提交成功", res[1] || "")
                        root.reload()
                    } else {
                        Fluent.NotificationManager.toast.error(root, "提交失败", res[1] || "")
                    }
                }
                onMenuItemClicked: function(index, text) {
                    if (index !== 0) return
                    // amend 需要一条新消息(输入框内容);为空则提示
                    if (commitInput.text.length === 0) {
                        Fluent.NotificationManager.toast.warning(root, "无法修补", "请先在输入框填写修补后的提交消息")
                        return
                    }
                    // 已推送的提交被 amend 会与远端历史分叉,需强制推送 → 弹危险确认
                    if (GitBridge.isHeadPushed())
                        amendDanger.start()
                    else
                        root.doAmend()
                }
            }
            Fluent.Button {
                text: "一键提交推送"
                enabled: commitInput.text.length > 0
                onClicked: {
                    GitBridge.quickCommitPush(commitInput.text)
                    commitInput.text = ""
                }
            }
        }

        // ---------- 主体分栏 ----------
        Fluent.SplitPane {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal
            splitPosition: 0.35

            firstContent: Item {
                anchors.fill: parent

                ColumnLayout {
                    anchors.fill: parent
                    anchors.rightMargin: Fluent.Enums.spacing.m
                    spacing: Fluent.Enums.spacing.s

                    // 文件列表工具条
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "变更 (" + changeModel.count + ")"
                            color: Fluent.Enums.textColor.primary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.bodyLarge
                            font.bold: true
                        }
                        Item { Layout.fillWidth: true }
                        Fluent.Button {
                            text: "全部暂存"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: GitBridge.stageAll()
                        }
                        Fluent.Button {
                            text: "全部取消"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: GitBridge.unstageAll()
                        }
                    }

                    // 变更文件列表(卡片容器 + 空状态)
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Fluent.Enums.radius.large
                        color: Fluent.Enums.cardColor
                        border.width: Fluent.Enums.border.normal
                        border.color: Fluent.Enums.stateColor.border

                        // 空状态:工作区干净
                        Fluent.EmptyState {
                            anchors.centerIn: parent
                            visible: changeModel.count === 0
                            icon: Fluent.Enums.icon.checkmark_circle
                            title: "工作区干净"
                            description: "没有未提交的变更"
                        }

                        Loader {
                            id: changeListLoader
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.xs
                            active: root._changeListActive && changeModel.count > 0
                            visible: active
                            sourceComponent: changeListComponent
                        }

                        Component {
                            id: changeListComponent

                            Fluent.ScrollArea {
                                id: changeScrollArea
                                type: Fluent.Enums.scroll.type_list
                                model: changeModel
                                itemHeight: 40
                                listSpacing: 2
                                listCacheBuffer: 0
                                reuseItems: false
                                bounceEnabled: false
                                padding: 0

                                delegate: Rectangle {
                                    width: ListView.view ? ListView.view.width : 0
                                    height: 40
                                    radius: Fluent.Enums.radius.small
                                    color: hover.hovered ? Fluent.Enums.stateColor.hover : "transparent"

                                    HoverHandler { id: hover }
                                    TapHandler { onTapped: root.showDiff(model.path, model.staged) }

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: Fluent.Enums.spacing.m
                                        anchors.rightMargin: Fluent.Enums.spacing.s
                                        spacing: Fluent.Enums.spacing.m

                                        Text {
                                            text: model.statusText
                                            Layout.preferredWidth: 50
                                            color: model.staged ? Fluent.Enums.statusLevel.successColor : Fluent.Enums.textColor.tertiary
                                            font.family: Fluent.Enums.fontFamily
                                            font.pixelSize: Fluent.Enums.typography.caption
                                        }
                                        Text {
                                            Layout.fillWidth: true
                                            text: model.path
                                            color: Fluent.Enums.textColor.primary
                                            font.family: Fluent.Enums.fontFamily
                                            font.pixelSize: Fluent.Enums.typography.body
                                            elide: Text.ElideMiddle
                                        }
                                        Fluent.Button {
                                            text: model.staged ? "取消" : "暂存"
                                            style: Fluent.Enums.button.style_transparent
                                            visible: hover.hovered
                                            onClicked: {
                                                if (model.staged) GitBridge.unstageFile(model.path)
                                                else GitBridge.stageFile(model.path)
                                            }
                                        }
                                        Fluent.Button {
                                            text: "丢弃"
                                            style: Fluent.Enums.button.style_transparent
                                            visible: hover.hovered && !model.staged
                                            onClicked: {
                                                discardDanger.content = "将丢弃 " + model.path
                                                    + " 的工作区改动。\n此操作不可恢复。"
                                                discardDanger._path = model.path
                                                discardDanger.start()
                                            }
                                        }
                                        Fluent.Button {
                                            text: "历史"
                                            style: Fluent.Enums.button.style_transparent
                                            visible: hover.hovered
                                            onClicked: fileHistoryDialog.openFor(model.path)
                                        }
                                    }
                                }
                            }
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

                    // 空状态:未选择文件
                    Fluent.EmptyState {
                        anchors.centerIn: parent
                        visible: root.selectedPath === ""
                        icon: Fluent.Enums.icon.document
                        title: "查看文件差异"
                        description: "从左侧变更列表选择一个文件"
                    }

                    Flickable {
                        id: diffFlick
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.l
                        clip: true
                        visible: root.selectedPath !== ""
                        contentWidth: diffView.paintedWidth
                        contentHeight: diffView.paintedHeight

                        TextEdit {
                            id: diffView
                            width: diffFlick.width
                            readOnly: true
                            selectByMouse: true
                            textFormat: TextEdit.RichText
                            wrapMode: TextEdit.NoWrap
                            font.family: "Consolas, Cascadia Code, monospace"
                            font.pixelSize: Fluent.Enums.typography.body
                            color: Fluent.Enums.textColor.primary
                            text: ""
                        }
                    }
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        title: "选择 Git 仓库目录"
        onAccepted: {
            var path = selectedFolder.toString().replace(/^file:\/\/\//, "")
            GitBridge.openRepoAsync(path)
        }
    }

    // 克隆对话框
    CloneDialog {
        id: cloneDialog
        onCloneRequested: function(url, path) { GitBridge.clone(url, path) }
    }

    // 初始化:先选目录,再走引导
    FolderDialog {
        id: initFolderDialog
        title: "选择要初始化的目录"
        onAccepted: {
            var path = selectedFolder.toString().replace(/^file:\/\/\//, "")
            var res = GitBridge.initRepo(path)
            if (res[0]) {
                GitBridge.openRepoAsync(path)
                initGuide.repoPath = path
                initGuide.currentIndex = 0
                initGuide.show()
            } else {
                console.warn("初始化失败:", res[1])
            }
        }
    }

    // 初始化引导(窗口)
    InitRepoGuide {
        id: initGuide
        onCompleted: function(p) { root.reload() }
    }

    // 文件历史
    FileHistoryDialog { id: fileHistoryDialog }

    // 指定远程/分支执行同步操作
    Fluent.MessageBox {
        id: syncDialog
        property string _mode: "pull"
        title: {
            if (_mode === "pull") return "指定拉取"
            if (_mode === "pullRebase") return "指定变基拉取"
            if (_mode === "fetch") return "指定抓取远程"
            if (_mode === "push") return "指定推送"
            return "指定强制推送"
        }
        confirmText: _mode === "pushForce" ? "继续" : "执行"
        cancelText: "取消"

        function openFor(mode) {
            _mode = mode
            syncRemoteInput.text = root._defaultRemoteName()
            syncBranchInput.text = root._defaultBranchName()
            open()
        }

        function validate() {
            var remote = syncRemoteInput.text.trim()
            var branch = syncBranchInput.text.trim()
            if (remote.length === 0) return false
            return _mode === "fetch" || branch.length > 0
        }

        onAccepted: {
            var remote = syncRemoteInput.text.trim()
            var branch = syncBranchInput.text.trim()
            if (_mode === "fetch") {
                GitBridge.fetchRemote(remote)
            } else if (_mode === "pull") {
                GitBridge.pullFrom(remote, branch)
            } else if (_mode === "pullRebase") {
                GitBridge.pullRebaseFrom(remote, branch)
            } else if (_mode === "push") {
                GitBridge.pushTo(remote, branch)
            } else if (_mode === "pushForce") {
                forcePushDanger._remote = remote
                forcePushDanger._branch = branch
                forcePushDanger.start()
            }
        }

        ColumnLayout {
            width: 360
            spacing: Fluent.Enums.spacing.m
            Fluent.LineEdit {
                id: syncRemoteInput
                Layout.fillWidth: true
                placeholderText: "远程名"
            }
            Fluent.LineEdit {
                id: syncBranchInput
                Layout.fillWidth: true
                visible: syncDialog._mode !== "fetch"
                placeholderText: "分支名"
            }
        }
    }

    // 危险操作:丢弃工作区改动二次确认(不可恢复)
    DangerDialog {
        id: discardDanger
        title: "确认丢弃改动"
        countdown: 3
        property string _path: ""
        onConfirmed: {
            var ok = GitBridge.discardFile(_path)
            if (ok)
                Fluent.NotificationManager.toast.success(root, "已丢弃", _path)
            else
                Fluent.NotificationManager.toast.error(root, "失败", "丢弃失败: " + _path)
        }
    }

    // 危险操作:强制推送二次确认(会覆盖远端历史,可能丢失他人提交,不可恢复)
    DangerDialog {
        id: forcePushDanger
        title: "确认强制推送"
        property string _remote: ""
        property string _branch: ""
        content: "⚠️ 强制推送(--force-with-lease)会用本地分支覆盖远端。\n"
            + "若远端有你本地没有的提交,可能造成丢失。\n此操作不可恢复,请确认远端历史可被覆盖。"
            + (_remote !== "" ? "\n目标: " + _remote + "/" + _branch : "")
        countdown: 3
        // 异步执行,结果经全局 operationFinished 统一弹 toast(与普通 push 一致)
        onConfirmed: {
            if (_remote !== "") GitBridge.pushForceTo(_remote, _branch)
            else GitBridge.pushForce()
            _remote = ""
            _branch = ""
        }
    }

    // 危险操作:远程覆盖本地二次确认(会丢弃已跟踪文件的本地改动和本地未推送提交)
    DangerDialog {
        id: forceResetToUpstreamDanger
        title: "确认远程覆盖本地"
        content: "远程覆盖本地会先抓取当前分支的上游,再将本地分支 hard reset 到上游。\n"
            + "已跟踪文件的本地未提交改动和本地未推送提交都会被丢弃。\n"
            + "此操作不可恢复,请确认远程版本就是要保留的版本。"
        countdown: 3
        // 异步执行,结果经全局 operationFinished 统一弹 toast(与普通 pull/push 一致)
        onConfirmed: GitBridge.forceResetToUpstream()
    }

    // 危险操作:修补「已推送」的提交(会与远端历史分叉,之后需强制推送才能同步)
    DangerDialog {
        id: amendDanger
        title: "确认修补已推送的提交"
        content: "⚠️ 最近一次提交已推送到远端。\n"
            + "修补(amend)会重写它,导致本地与远端历史分叉,\n"
            + "之后需要「强制推送」才能同步。若他人已基于旧提交工作,可能造成影响。"
        countdown: 3
        onConfirmed: root.doAmend()
    }

}
