import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

ColumnLayout {
    id: root

    property bool compact: false
    property alias scopeIndex: scopeCombo.currentIndex
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
        text: "控制规划范围和生成内容。"
        textFormat: Text.PlainText
        color: Fluent.Enums.textColor.tertiary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.caption
        wrapMode: Text.WordWrap
    }

    GridLayout {
        id: rulesFields
        Layout.fillWidth: true
        columns: root.compact ? 1 : 2
        columnSpacing: Fluent.Enums.spacing.m
        rowSpacing: Fluent.Enums.spacing.s

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 1
            spacing: Fluent.Enums.spacing.xxs

            Text {
                text: "规划范围"
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }

            Fluent.ComboBox {
                id: scopeCombo
                Layout.fillWidth: true
                model: ["提交规划：仅已暂存差异", "提交规划：全部工作区改动"]
                currentIndex: 0
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 1
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
            Layout.columnSpan: rulesFields.columns
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
                        text: "仅本机回环 Ollama 直接发送；非本机 Ollama 与远程 API 每次发送前都会确认范围。"
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
}
