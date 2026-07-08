// Stash 视图(阶段 3:迁移 stash_dialog.py,改为导航页)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Item {
    id: root
    property string _stashRequestRepoPath: ""
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
            Fluent.NotificationManager.toast.success(root, "成功", res[1] || "操作完成")
            root.reload()
        } else {
            Fluent.NotificationManager.toast.error(root, "失败", res[1] || "操作失败")
        }
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
            RowLayout {
                width: parent.cw
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
                        root._op(GitBridge.stashSave(stashMsgInput.text))
                        stashMsgInput.text = ""
                    }
                }
                Fluent.Button {
                    text: "清空所有"
                    enabled: stashModel.count > 0
                    onClicked: root._op(GitBridge.stashClear())
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
                        Fluent.Button { text: "应用"; style: Fluent.Enums.button.style_transparent; onClicked: root._op(GitBridge.stashApply(model.id)) }
                        Fluent.Button { text: "恢复"; onClicked: root._op(GitBridge.stashPop(model.id)) }
                        Fluent.Button { text: "删除"; style: Fluent.Enums.button.style_transparent; onClicked: root._op(GitBridge.stashDrop(model.id)) }
                    }
                }
            }
        }
    }
}
