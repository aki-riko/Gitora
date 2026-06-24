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
    property var selected: []   // 选中的 commit hash 列表(最多2)
    ListModel { id: histModel }

    function openFor(path) {
        dlg.filePath = path
        dlg.title = "文件历史 - " + path
        dlg.selected = []
        histModel.clear()
        rightArea.text = "加载中..."
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
            rightArea.text = "加载中..."
            GitBridge.requestFileContentAtCommit(dlg.filePath, dlg.selected[0])
        } else if (dlg.selected.length === 2) {
            rightArea.text = "加载中..."
            GitBridge.requestDiffBetween(dlg.filePath, dlg.selected[0], dlg.selected[1])
        } else {
            rightArea.text = "选择一个提交查看该版本内容,选择两个对比差异"
        }
    }

    Connections {
        target: GitBridge
        function onFileHistoryReady(path, list) {
            if (path !== dlg.filePath) return  // 防过期
            histModel.clear()
            for (var i = 0; i < list.length; i++) histModel.append(list[i])
            if (dlg.selected.length === 0)
                rightArea.text = list.length > 0 ? "选择一个提交查看该版本内容,选择两个对比差异" : "无历史记录"
        }
        function onFileContentReady(path, hash, content) {
            if (path !== dlg.filePath || dlg.selected.length !== 1 || hash !== dlg.selected[0]) return
            rightArea.text = content || "(空文件)"
        }
        function onDiffBetweenReady(path, c1, c2, diff) {
            if (path !== dlg.filePath || dlg.selected.length !== 2
                || c1 !== dlg.selected[0] || c2 !== dlg.selected[1]) return
            rightArea.text = diff || "(无差异)"
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

            ListView {
                id: histList
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.xs
                clip: true
                spacing: 2
                model: histModel
                delegate: Rectangle {
                    width: histList.width
                    height: 48
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

            Flickable {
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                clip: true
                contentWidth: rightArea.paintedWidth
                contentHeight: rightArea.paintedHeight
                TextEdit {
                    id: rightArea
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.NoWrap
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    color: Fluent.Enums.textColor.primary
                }
            }
        }
    }
}
