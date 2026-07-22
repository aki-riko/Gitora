import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

ColumnLayout {
    id: root

    property bool compact: false
    property alias generateBody: bodySwitch.checked

    spacing: Fluent.Enums.spacing.s

    Text {
        Layout.fillWidth: true
        text: "生成规则"
        textFormat: Text.PlainText
        color: Fluent.Enums.textColor.primary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.body
        font.bold: true
    }

    Text {
        Layout.fillWidth: true
        text: "AI 提交固定分析并提交整个工作区；这里仅控制是否生成正文。"
        textFormat: Text.PlainText
        color: Fluent.Enums.textColor.tertiary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.caption
        wrapMode: Text.WordWrap
    }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: bodyOptionLayout.implicitHeight + Fluent.Enums.spacing.s * 2
        radius: Fluent.Enums.radius.small
        color: Fluent.Enums.stateColor.actionsRowBg
        border.color: Fluent.Enums.stateColor.settingCardBorder
        border.width: Fluent.Enums.border.thin

        RowLayout {
            id: bodyOptionLayout
            anchors.fill: parent
            anchors.margins: Fluent.Enums.spacing.s
            spacing: Fluent.Enums.spacing.m

            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: Fluent.Enums.spacing.xxs

                Text {
                    Layout.fillWidth: true
                    text: "生成提交正文"
                    textFormat: Text.PlainText
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.body
                }

                Text {
                    Layout.fillWidth: true
                    text: "在提交标题之外补充变更说明。"
                    textFormat: Text.PlainText
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    wrapMode: Text.WordWrap
                }
            }

            Fluent.ToggleSwitch {
                id: bodySwitch
                type: Fluent.Enums.toggle.type_indicator
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        implicitHeight: boundaryLayout.implicitHeight + Fluent.Enums.spacing.s * 2
        radius: Fluent.Enums.radius.small
        color: Fluent.Enums.stateColor.actionsRowBg

        RowLayout {
            id: boundaryLayout
            anchors.fill: parent
            anchors.margins: Fluent.Enums.spacing.s
            spacing: Fluent.Enums.spacing.s

            Rectangle {
                width: 8
                height: 8
                radius: 4
                color: Fluent.Enums.statusLevel.getColor(
                    Fluent.Enums.statusLevel.infoStr
                )
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: 5
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Fluent.Enums.spacing.xxs

                Text {
                    Layout.fillWidth: true
                    text: "发送边界"
                    textFormat: Text.PlainText
                    color: Fluent.Enums.textColor.secondary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: "点击“AI 提交”会把已暂存、未暂存和未跟踪改动一起发送给所选模型；仅本机回环 Ollama 保证源码不离开本机。"
                    textFormat: Text.PlainText
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
