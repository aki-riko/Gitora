// 冲突视图(阶段 3:迁移 conflict_interface.py)
import QtQuick
import QtQuick.Layouts

import FluentQML as Fluent
import "../components"

Item {
    id: root

    property bool merging: false
    ListModel { id: conflictModel }

    function reload() {
        conflictModel.clear()
        if (!GitBridge || !GitBridge.repoPath) return
        root.merging = GitBridge.isMerging()
        var list = GitBridge.getConflicts()
        for (var i = 0; i < list.length; i++) conflictModel.append(list[i])
    }

    function _op(res) {
        console.log("冲突操作:", res[0], res[1])
        if (res[0]) root.reload()
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
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
                    text: "冲突解决"
                    font.pixelSize: Fluent.Enums.typography.displayLarge
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                }
                Item { Layout.fillWidth: true }
                Fluent.Button { text: "刷新"; icon: Fluent.Enums.icon.arrow_sync; onClicked: root.reload() }
                Fluent.Button {
                    text: "中止合并"
                    visible: root.merging
                    onClicked: root._op(GitBridge.abortMerge())
                }
            }

            // 状态卡片
            Fluent.Card {
                width: parent.cw
                height: statusRow.implicitHeight + Fluent.Enums.spacing.l * 2
                RowLayout {
                    id: statusRow
                    anchors.centerIn: parent
                    width: parent.width - Fluent.Enums.spacing.l * 2
                    spacing: Fluent.Enums.spacing.m
                    Fluent.Icon {
                        icon: root.merging ? Fluent.Enums.icon.warning : Fluent.Enums.icon.checkmark_circle
                        iconSize: Fluent.Enums.iconSize.l
                        color: root.merging ? Fluent.Enums.statusLevel.warningColor : Fluent.Enums.statusLevel.successColor
                    }
                    Text {
                        Layout.fillWidth: true
                        text: !root.merging ? "当前没有合并冲突"
                              : (conflictModel.count > 0 ? ("发现 " + conflictModel.count + " 个冲突文件") : "合并中,冲突已解决")
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.body
                    }
                }
            }

            // 冲突文件列表
            Column {
                width: parent.cw
                spacing: Fluent.Enums.spacing.m
                visible: conflictModel.count > 0

                Text {
                    text: "冲突文件"
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.subtitle
                    font.bold: true
                }

                Repeater {
                    model: conflictModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: confRow.implicitHeight + Fluent.Enums.spacing.m * 2
                        RowLayout {
                            id: confRow
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.m
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.document_error
                                iconSize: Fluent.Enums.iconSize.l
                                color: Fluent.Enums.statusLevel.warningColor
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    Layout.fillWidth: true
                                    text: model.path
                                    color: Fluent.Enums.textColor.primary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.body
                                    elide: Text.ElideMiddle
                                }
                                Text {
                                    text: model.hasConflictMarkers ? "含冲突标记 <<<<<<< >>>>>>>" : "二进制或删除冲突"
                                    color: Fluent.Enums.textColor.tertiary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.caption
                                }
                            }
                            Fluent.Button {
                                text: "查看冲突"
                                style: Fluent.Enums.button.style_transparent
                                visible: model.hasConflictMarkers
                                onClicked: conflictViewer.openFor(model.path)
                            }
                            Fluent.Button {
                                text: "使用我们的"
                                onClicked: root._op(GitBridge.resolveWithOurs(model.path))
                            }
                            Fluent.Button {
                                text: "使用他们的"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: root._op(GitBridge.resolveWithTheirs(model.path))
                            }
                        }
                    }
                }
            }
        }
    }

    // 冲突内容查看
    ConflictViewerDialog { id: conflictViewer }
}
