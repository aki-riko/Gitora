import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.DialogBoxCore {
    id: dlg

    property string planSummary: ""
    property var planGroups: []
    property real windowScale: 0.9

    readonly property int targetDialogWidth: Math.max(
        Fluent.Enums.dialog.minWidth,
        Math.floor(dlg.width * dlg.windowScale))
    readonly property int targetDialogHeight: Math.max(
        Fluent.Enums.dialog.actionsRowHeight
            + Fluent.Enums.dialog.contentPadding,
        Math.floor(dlg.height * dlg.windowScale))
    readonly property int targetBodyHeight: Math.max(
        0,
        dlg.targetDialogHeight
            - Fluent.Enums.dialog.actionsRowHeight
            - Fluent.Enums.dialog.contentPadding)

    contentWidth: dlg.targetDialogWidth - Fluent.Enums.dialog.contentPadding

    footer: Component {
        RowLayout {
            spacing: Fluent.Enums.spacing.l

            Fluent.ButtonCore {
                text: "不采用"
                style: Fluent.Enums.button.style_filled
                level: Fluent.Enums.statusLevel.error
                width: Fluent.Enums.dialog.buttonWidth
                height: Fluent.Enums.dialog.buttonHeight
                onClicked: dlg.reject()
            }

            Fluent.ButtonCore {
                text: "采用并提交推送"
                style: Fluent.Enums.button.style_filled
                level: Fluent.Enums.statusLevel.success
                width: Fluent.Enums.dialog.buttonWidth
                    + Fluent.Enums.spacing.xxxl * 2
                height: Fluent.Enums.dialog.buttonHeight
                onClicked: dlg.accept()
            }
        }
    }

    function openPlan(summary, groups) {
        dlg.planSummary = summary || ""
        dlg.planGroups = groups || []
        dlg.open()
    }

    ColumnLayout {
        width: dlg.contentWidth
        height: dlg.targetBodyHeight
        spacing: Fluent.Enums.spacing.l

        Text {
            Layout.fillWidth: true
            text: "AI 提交方案"
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.subtitle
            font.bold: true
        }

        Text {
            Layout.fillWidth: true
            text: "将按 AI 规划创建 " + dlg.planGroups.length + " 个 Commit"
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.bodyLarge
            font.bold: true
        }

        Text {
            Layout.fillWidth: true
            visible: text.length > 0
            text: dlg.planSummary
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.secondary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
            wrapMode: Text.WordWrap
        }

        Fluent.Separator { Layout.fillWidth: true }

        Fluent.ScrollArea {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            padding: 0

            Column {
                width: parent ? parent.width : 0
                spacing: Fluent.Enums.spacing.s

                Repeater {
                    model: dlg.planGroups

                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: parent ? parent.width : 0
                        height: groupColumn.implicitHeight
                            + Fluent.Enums.spacing.m * 2
                        radius: Fluent.Enums.radius.small
                        color: Fluent.Enums.stateColor.settingCardBg
                        border.width: Fluent.Enums.border.normal
                        border.color: Fluent.Enums.stateColor.settingCardBorder

                        ColumnLayout {
                            id: groupColumn
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.m
                            spacing: Fluent.Enums.spacing.xxs

                            Text {
                                Layout.fillWidth: true
                                text: "Commit " + (index + 1) + " · "
                                    + (modelData.title || "未命名")
                                textFormat: Text.PlainText
                                color: Fluent.Enums.textColor.primary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.body
                                font.bold: true
                                wrapMode: Text.WordWrap
                            }

                            Text {
                                Layout.fillWidth: true
                                text: (modelData.changes || []).length
                                    + " 个改动"
                                textFormat: Text.PlainText
                                color: Fluent.Enums.textColor.tertiary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.caption
                            }

                            Text {
                                Layout.fillWidth: true
                                visible: text.length > 0
                                text: modelData.body || ""
                                textFormat: Text.PlainText
                                color: Fluent.Enums.textColor.secondary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.caption
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }
    }
}
