// 文件历史对话框(阶段 5:迁移 file_history_dialog.py)
// 左:文件提交历史列表(可选最多2个) / 右:选1看内容,选2看版本diff
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "文件历史"
    confirmText: "关闭"
    cancelButtonVisible: false

    property string filePath: ""
    property string _requestRepoPath: ""
    property var selected: []   // 选中的 commit hash 列表(最多2)
    property bool _showingDiff: false
    ListModel { id: histModel }

    function clearContent() {
        dlg.filePath = ""
        dlg._requestRepoPath = ""
        dlg.selected = []
        dlg._showingDiff = false
        histModel.clear()
        rightArea.text = ""
        historyDiffViewer.clearDiff()
    }

    function openFor(path) {
        dlg.filePath = path
        dlg._requestRepoPath = (GitBridge && GitBridge.repoPath) ? GitBridge.repoPath : ""
        dlg.title = "文件历史 - " + path
        dlg.selected = []
        dlg._showingDiff = false
        histModel.clear()
        rightArea.text = "加载中..."
        historyDiffViewer.clearDiff()
        GitBridge.requestFileHistory(path, 50)  // 异步,经 fileHistoryReady 回传
        dlg.open()
    }

    function _toggleSelect(hash) {
        var arr = dlg.selected.slice()
        var idx = arr.indexOf(hash)
        if (idx >= 0) arr.splice(idx, 1)
        else {
            if (arr.length >= 2) arr.shift()  // 超过2个,移除最早的
            arr.push(hash)
        }
        dlg.selected = arr
        _refreshRight()
    }

    function _refreshRight() {
        if (dlg.selected.length === 1) {
            dlg._showingDiff = false
            rightArea.text = "加载中..."
            GitBridge.requestFileContentAtCommit(dlg.filePath, dlg.selected[0])
        } else if (dlg.selected.length === 2) {
            dlg._showingDiff = true
            historyDiffViewer.setLoading("加载中...")
            GitBridge.requestDiffBetween(dlg.filePath, dlg.selected[0], dlg.selected[1])
        } else {
            dlg._showingDiff = false
            rightArea.text = "选择一个提交查看该版本内容,选择两个对比差异"
        }
    }

    Connections {
        target: GitBridge
        function onRepoPathChanged(path) { dlg.clearContent() }
        function onFileHistoryReady(repoPath, path, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath || path !== dlg.filePath) return  // 防过期
            histModel.clear()
            for (var i = 0; i < list.length; i++) histModel.append(list[i])
            if (dlg.selected.length === 0) {
                dlg._showingDiff = false
                rightArea.text = list.length > 0 ? "选择一个提交查看该版本内容,选择两个对比差异" : "无历史记录"
            }
        }
        function onFileContentReady(repoPath, path, hash, content) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath
                || path !== dlg.filePath || dlg.selected.length !== 1 || hash !== dlg.selected[0]) return
            dlg._showingDiff = false
            rightArea.text = content || "(空文件)"
        }
        function onDiffBetweenReady(repoPath, path, c1, c2, diff) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath
                || path !== dlg.filePath || dlg.selected.length !== 2
                || c1 !== dlg.selected[0] || c2 !== dlg.selected[1]) return
            dlg._showingDiff = true
            historyDiffViewer.rawDiff = diff || ""
        }
    }

    RowLayout {
        width: 720
        height: 440
        spacing: Fluent.Enums.spacing.m

        // 左:提交历史列表
        Rectangle {
            Layout.preferredWidth: 280
            Layout.fillHeight: true
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border

            Fluent.ScrollArea {
                id: histList
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.xs
                type: Fluent.Enums.scroll.type_list
                itemHeight: Fluent.Enums.controlSize.buttonHeight + Fluent.Enums.spacing.xl
                listSpacing: Fluent.Enums.spacing.xxs
                reuseItems: true
                bounceEnabled: false
                padding: 0
                model: histModel
                delegate: Rectangle {
                    width: ListView.view ? ListView.view.width : 0
                    height: histList.itemHeight
                    radius: Fluent.Enums.radius.micro
                    readonly property bool isSel: dlg.selected.indexOf(model.hash) >= 0
                    color: isSel ? Fluent.Enums.stateColor.hover : (hov.hovered ? Fluent.Enums.stateColor.hover : "transparent")
                    border.width: isSel ? Fluent.Enums.border.normal : 0
                    border.color: Fluent.Enums.accentColor

                    HoverHandler { id: hov }
                    TapHandler { onTapped: dlg._toggleSelect(model.hash) }

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.s
                        spacing: 0
                        Text {
                            Layout.fillWidth: true
                            text: model.message
                            color: Fluent.Enums.textColor.primary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.caption
                            elide: Text.ElideRight
                        }
                        Text {
                            text: model.shortHash + " · " + model.date
                            color: Fluent.Enums.textColor.tertiary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.caption
                        }
                    }
                }
            }
        }

        // 右:内容/diff
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border

            Fluent.ScrollArea {
                id: rightScrollArea
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                visible: !dlg._showingDiff
                orientation: Qt.Horizontal | Qt.Vertical
                padding: 0
                TextEdit {
                    id: rightArea
                    width: Math.max(parent ? parent.width : 0, paintedWidth)
                    height: Math.max(1, paintedHeight)
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.NoWrap
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    color: Fluent.Enums.textColor.primary
                }
            }
            DiffViewer {
                id: historyDiffViewer
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                visible: dlg._showingDiff
            }
        }
    }
}
