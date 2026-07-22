// Stash 视图(阶段 3:迁移 stash_dialog.py,改为导航页)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent
import "../components"

Item {
    id: root
    property string _stashRequestRepoPath: ""
    property string _pendingDrop: ""
    property string _pendingBranchStash: ""
    property string _showTitle: ""
    ListModel { id: stashModel }

    function clearModel() {
        root._stashRequestRepoPath = ""
        stashModel.clear()
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) { clearModel(); return }
        root._stashRequestRepoPath = GitBridge.repoPath
        GitBridge.requestStashList()  // 异步,结果经 stashListReady 回传
    }

    function _op(res) {
        if (res[0]) {
            Fluent.NotificationManager.desktop.success("成功", res[1] || "操作完成")
            root.reload()
        } else {
            Fluent.NotificationManager.desktop.error("失败", res[1] || "操作失败")
        }
    }

    function _openBranchDialog(stashId) {
        root._pendingBranchStash = stashId
        var match = /stash@\{(\d+)\}/.exec(stashId)
        stashBranchNameInput.text = match ? ("stash-" + match[1]) : ""
        stashBranchDialog.open()
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onRepoPathChanged(path) {
            root.clearModel()
            root.reload()
        }
        function onStashListReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== root._stashRequestRepoPath) return
            stashModel.clear()
            for (var i = 0; i < list.length; i++) stashModel.append(list[i])
        }
    }
    Component.onCompleted: root.reload()

    Fluent.ScrollArea {
        anchors.fill: parent
        Column {
            id: stashCol
            width: parent ? parent.width : 0
            spacing: Fluent.Enums.spacing.l
            topPadding: Fluent.Enums.spacing.xl
            bottomPadding: Fluent.Enums.spacing.xl
            property real sidePad: Math.max(Fluent.Enums.spacing.xxl, (width - 980) / 2)
            leftPadding: sidePad
            rightPadding: sidePad
            readonly property real cw: width - sidePad * 2

            Text {
                text: "暂存 (Stash)"
                font.pixelSize: Fluent.Enums.typography.displayLarge
                font.bold: true
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
            }

            // 保存操作栏
            Column {
                width: parent.cw
                spacing: Fluent.Enums.spacing.m
                RowLayout {
                    width: parent.width
                    spacing: Fluent.Enums.spacing.m
                    Fluent.LineEdit {
                        id: stashMsgInput
                        Layout.fillWidth: true
                        placeholderText: "备注(可选)"
                    }
                    Fluent.Button {
                        text: "保存当前修改"
                        style: Fluent.Enums.button.style_primary
                        onClicked: {
                            root._op(GitBridge.stashSave(stashMsgInput.text, includeUntrackedCheck.checked, keepIndexCheck.checked))
                            stashMsgInput.text = ""
                        }
                    }
                    Fluent.Button {
                        text: "清空所有"
                        enabled: stashModel.count > 0
                        onClicked: clearStashDanger.start()
                    }
                }
                RowLayout {
                    width: parent.width
                    spacing: Fluent.Enums.spacing.l
                    Fluent.CheckBox {
                        id: includeUntrackedCheck
                        text: "包含未跟踪文件"
                    }
                    Fluent.CheckBox {
                        id: keepIndexCheck
                        text: "保留暂存区"
                    }
                }
            }

            // 空状态
            Text {
                width: parent.cw
                visible: stashModel.count === 0
                text: "暂无保存记录"
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                horizontalAlignment: Text.AlignHCenter
                topPadding: Fluent.Enums.spacing.xxl
            }

            // stash 列表
            Repeater {
                model: stashModel
                delegate: Fluent.Card {
                    width: stashCol.cw
                    height: stashRow.implicitHeight + Fluent.Enums.spacing.l * 2
                    RowLayout {
                        id: stashRow
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.l
                        spacing: Fluent.Enums.spacing.m
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Text {
                                text: model.id
                                color: Fluent.Enums.accentColor
                                font.family: "Consolas, monospace"
                                font.pixelSize: Fluent.Enums.typography.caption
                            }
                            Text {
                                Layout.fillWidth: true
                                text: model.message
                                color: Fluent.Enums.textColor.primary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.body
                                elide: Text.ElideRight
                            }
                        }
                        Fluent.Button {
                            text: "查看"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: {
                                var res = GitBridge.stashShow(model.id)
                                if (res[0]) {
                                    root._showTitle = model.id
                                    stashShowText.text = res[1] || ""
                                    stashShowDialog.open()
                                } else {
                                    Fluent.NotificationManager.desktop.error("失败", res[1] || "查看 stash 失败")
                                }
                            }
                        }
                        Fluent.Button { text: "应用"; style: Fluent.Enums.button.style_transparent; onClicked: root._op(GitBridge.stashApply(model.id)) }
                        Fluent.Button { text: "恢复"; onClicked: root._op(GitBridge.stashPop(model.id)) }
                        Fluent.Button {
                            text: "建分支"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: root._openBranchDialog(model.id)
                        }
                        Fluent.Button {
                            text: "删除"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: {
                                root._pendingDrop = model.id
                                dropStashDanger.start()
                            }
                        }
                    }
                }
            }
        }
    }

    Fluent.MessageBox {
        id: stashBranchDialog
        title: "从 Stash 建分支"
        confirmText: "创建"
        cancelText: "取消"
        ColumnLayout {
            width: 420
            spacing: Fluent.Enums.spacing.m
            Text {
                Layout.fillWidth: true
                text: root._pendingBranchStash
                color: Fluent.Enums.textColor.tertiary
                font.family: "Consolas, monospace"
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideRight
            }
            Text {
                Layout.fillWidth: true
                text: "成功后会切换到新分支,并按 Git 行为移除这条 stash 记录。"
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                wrapMode: Text.WordWrap
            }
            Fluent.LineEdit {
                id: stashBranchNameInput
                Layout.fillWidth: true
                placeholderText: "新分支名"
            }
        }
        onAccepted: {
            root._op(GitBridge.stashBranch(stashBranchNameInput.text, root._pendingBranchStash))
            root._pendingBranchStash = ""
        }
    }

    Fluent.MessageBox {
        id: stashShowDialog
        title: "Stash 内容 " + root._showTitle
        confirmText: "关闭"
        cancelText: "关闭"
        ColumnLayout {
            width: 720
            spacing: Fluent.Enums.spacing.m
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 420
                radius: Fluent.Enums.radius.medium
                color: Fluent.Enums.cardColor
                border.width: Fluent.Enums.border.normal
                border.color: Fluent.Enums.stateColor.border
                Fluent.ScrollArea {
                    anchors.fill: parent
                    anchors.margins: Fluent.Enums.spacing.s
                    padding: 0
                    TextEdit {
                        id: stashShowText
                        readOnly: true
                        selectByMouse: true
                        textFormat: TextEdit.PlainText
                        wrapMode: TextEdit.NoWrap
                        font.family: "Consolas, monospace"
                        font.pixelSize: Fluent.Enums.typography.caption
                        color: Fluent.Enums.textColor.primary
                    }
                }
            }
        }
    }

    DangerDialog {
        id: dropStashDanger
        title: "确认删除 Stash"
        countdown: 3
        content: "将删除 \"" + root._pendingDrop + "\"。\n此操作会永久移除这条 stash 记录,不会修改当前工作区。"
        onConfirmed: {
            if (root._pendingDrop)
                root._op(GitBridge.stashDrop(root._pendingDrop))
            root._pendingDrop = ""
        }
    }

    DangerDialog {
        id: clearStashDanger
        title: "确认清空所有 Stash"
        countdown: 3
        content: "将清空当前仓库的所有 stash 记录。\n这些记录删除后不可从 Gitora 恢复。"
        onConfirmed: root._op(GitBridge.stashClear())
    }
}
