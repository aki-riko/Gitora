// Reflog 对话框(阶段 4:迁移 reflog_dialog.py)
// 引用日志列表 + 检出到指定提交
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "引用日志 (Reflog)"
    confirmText: "关闭"
    cancelButtonVisible: false

    signal checkoutRequested(string commitHash)
    ListModel { id: reflogModel }

    function openReflog() {
        reflogModel.clear()
        if (GitBridge && GitBridge.repoPath) {
            GitBridge.requestReflog(100)  // 异步,结果经 reflogReady 回传
        }
        dlg.open()
    }

    Connections {
        target: GitBridge
        function onReflogReady(list) {
            reflogModel.clear()
            for (var i = 0; i < list.length; i++) reflogModel.append(list[i])
        }
    }

    ColumnLayout {
        width: 520

        ListView {
            id: reflogList
            Layout.fillWidth: true
            Layout.preferredHeight: 360
            clip: true
            spacing: Fluent.Enums.spacing.s
            model: reflogModel
            delegate: Fluent.Card {
                width: reflogList.width
                height: rlRow.implicitHeight + Fluent.Enums.spacing.m * 2
                RowLayout {
                    id: rlRow
                    anchors.fill: parent
                    anchors.margins: Fluent.Enums.spacing.m
                    spacing: Fluent.Enums.spacing.m
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        RowLayout {
                            spacing: Fluent.Enums.spacing.m
                            Text {
                                text: (model.hash || "").substring(0, 7)
                                color: Fluent.Enums.accentColor
                                font.family: "Consolas, monospace"
                                font.pixelSize: Fluent.Enums.typography.caption
                            }
                            Text {
                                text: model.ref
                                color: Fluent.Enums.textColor.tertiary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.caption
                            }
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
                        text: "检出"
                        style: Fluent.Enums.button.style_transparent
                        onClicked: dlg.checkoutRequested(model.hash)
                    }
                }
            }
        }
    }
}
