// 仓库视图(阶段 2:完整迁移 repo_interface.py)
// 布局:Header(仓库信息+操作) + SplitPane(左:文件列表+提交面板 / 右:Diff)
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs

import FluentQML as Fluent
import "../components"

Item {
    id: root

    // 当前选中的文件(用于 diff)
    property string selectedPath: ""
    property bool selectedStaged: false

    // ==================== 数据加载 ====================
    function reload() {
        if (!GitBridge || !GitBridge.repoPath) {
            branchLabel.text = ""
            changeModel.clear()
            root.selectedPath = ""
            diffView.text = ""
            return
        }
        // 后台获取,结果经 statusReady/branchReady 回填,不阻塞主线程
        GitBridge.requestStatus()
    }

    function showDiff(path, staged) {
        root.selectedPath = path
        root.selectedStaged = staged
        var raw = (GitBridge && path) ? GitBridge.getDiff(path, staged) : ""
        diffView.text = _diffToHtml(raw)
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
        function onStatusReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return  // 过期/切仓库,丢弃
            changeModel.clear()
            var stillThere = false
            for (var i = 0; i < list.length; i++) {
                changeModel.append(list[i])
                if (list[i].path === root.selectedPath) stillThere = true
            }
            // 选中的文件已不在变更列表(已暂存/提交/切仓库)→ 清空 diff,避免显示过期内容
            if (root.selectedPath !== "" && !stillThere) {
                root.selectedPath = ""
                diffView.text = ""
            }
        }
        function onBranchReady(repoPath, branch) {
            if (!GitBridge || repoPath !== GitBridge.repoPath) return
            branchLabel.text = branch
        }
        function onOperationFinished(ok, msg) {
            if (ok) {
                Fluent.NotificationManager.toast.success(root, "成功", msg || "操作完成")
                root.reload()
            } else {
                Fluent.NotificationManager.toast.error(root, "失败", msg || "操作失败")
            }
        }
        function onRepoOpened(ok, pathOrErr) {
            if (ok) openButton.rebuildList()
            else console.warn("打开仓库失败:", pathOrErr)
        }
    }

    Component.onCompleted: root.reload()

    ListModel { id: changeModel }

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
            Fluent.Button { text: "拉取"; icon: Fluent.Enums.icon.arrow_download; onClicked: GitBridge.pull() }
            Fluent.Button { text: "推送"; icon: Fluent.Enums.icon.arrow_upload; onClicked: GitBridge.push() }
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

                        Fluent.ListView {
                            id: changeListView
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.xs
                            visible: changeModel.count > 0
                            framed: false
                            spacing: 2
                            model: changeModel
                            delegate: Rectangle {
                                width: changeListView.listView ? changeListView.listView.width : 0
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
}
