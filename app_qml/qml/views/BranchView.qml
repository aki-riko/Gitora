// 分支视图(阶段 3:迁移 branch_interface.py)
import QtQuick
import QtQuick.Layouts

import FluentQML as Fluent

Item {
    id: root

    property string currentBranch: ""
    ListModel { id: localModel }
    ListModel { id: remoteModel }

    function reload() {
        localModel.clear()
        remoteModel.clear()
        if (!GitBridge || !GitBridge.repoPath) return
        root.currentBranch = GitBridge.getCurrentBranch()
        var list = GitBridge.getBranches()
        for (var i = 0; i < list.length; i++) {
            if (list[i].isRemote) remoteModel.append(list[i])
            else localModel.append(list[i])
        }
    }

    function _op(res) {
        console.log("分支操作:", res[0], res[1])
        if (res[0]) root.reload()
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onOperationFinished(ok, msg) { root.reload() }
    }
    Component.onCompleted: root.reload()

    Fluent.ScrollArea {
        anchors.fill: parent
        Column {
            width: parent ? parent.width : 0
            spacing: Fluent.Enums.spacing.l
            topPadding: Fluent.Enums.spacing.xl
            bottomPadding: Fluent.Enums.spacing.xl
            leftPadding: Fluent.Enums.spacing.xxl
            rightPadding: Fluent.Enums.spacing.xxl
            readonly property real cw: width - Fluent.Enums.spacing.xxl * 2

            // 标题栏
            RowLayout {
                width: parent.cw
                Text {
                    text: "分支"
                    font.pixelSize: Fluent.Enums.typography.displayLarge
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                }
                Item { Layout.fillWidth: true }
                Fluent.Button { text: "Fetch"; icon: Fluent.Enums.icon.arrow_sync; onClicked: GitBridge.fetch() }
                Fluent.Button { text: "Prune"; onClicked: root._op(GitBridge.pruneRemote()) }
                Fluent.Button {
                    text: "新建分支"
                    style: Fluent.Enums.button.style_primary
                    icon: Fluent.Enums.icon.add
                    onClicked: createDialog.open()
                }
            }

            // 本地分支
            Fluent.SettingsCardGroup {
                title: "本地分支"
                width: parent.cw
                Repeater {
                    model: localModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: lbRow.implicitHeight + Fluent.Enums.spacing.m * 2
                        RowLayout {
                            id: lbRow
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.m
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.branch_fork
                                iconSize: Fluent.Enums.iconSize.l
                                color: model.isCurrent ? Fluent.Enums.accentColor : Fluent.Enums.textColor.tertiary
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    text: model.name + (model.isCurrent ? "  (当前)" : "")
                                    color: Fluent.Enums.textColor.primary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.body
                                    font.bold: model.isCurrent
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: {
                                        var parts = []
                                        if (model.tracking) parts.push("跟踪 " + model.tracking)
                                        if (model.ahead > 0) parts.push("↑" + model.ahead)
                                        if (model.behind > 0) parts.push("↓" + model.behind)
                                        return parts.length > 0 ? parts.join("  ") : "本地分支"
                                    }
                                    color: Fluent.Enums.textColor.tertiary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.caption
                                    elide: Text.ElideRight
                                }
                            }
                            Fluent.Button {
                                text: model.isCurrent ? "当前" : "切换"
                                enabled: !model.isCurrent
                                onClicked: root._op(GitBridge.checkoutBranch(model.name))
                            }
                            Fluent.Button {
                                text: "删除"
                                style: Fluent.Enums.button.style_transparent
                                visible: !model.isCurrent
                                onClicked: root._op(GitBridge.deleteBranch(model.name, false))
                            }
                        }
                    }
                }
            }

            // 远程分支
            Fluent.SettingsCardGroup {
                title: "远程分支"
                width: parent.cw
                visible: remoteModel.count > 0
                Repeater {
                    model: remoteModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: rbRow.implicitHeight + Fluent.Enums.spacing.m * 2
                        RowLayout {
                            id: rbRow
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.m
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.branch_fork
                                iconSize: Fluent.Enums.iconSize.l
                                color: Fluent.Enums.textColor.tertiary
                            }
                            Text {
                                Layout.fillWidth: true
                                text: model.name
                                color: Fluent.Enums.textColor.primary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.body
                            }
                            Fluent.Button {
                                text: "检出"
                                onClicked: root._op(GitBridge.checkoutBranch(model.name))
                            }
                        }
                    }
                }
            }
        }
    }

    // 新建分支对话框
    Fluent.MessageBox {
        id: createDialog
        title: "新建分支"
        confirmText: "创建"
        cancelText: "取消"
        Fluent.LineEdit {
            id: newBranchInput
            width: 320
            placeholderText: "分支名称"
        }
        onAccepted: {
            if (newBranchInput.text)
                root._op(GitBridge.createBranch(newBranchInput.text, true))
            newBranchInput.text = ""
        }
    }
}
