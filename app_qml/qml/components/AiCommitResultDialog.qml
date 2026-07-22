import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.DialogBoxCore {
    id: dlg

    property string planTitle: ""
    property string planBody: ""
    property string planSummary: ""

    contentWidth: 520

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

    function openPlan(title, body, summary) {
        dlg.planTitle = title || ""
        dlg.planBody = body || ""
        dlg.planSummary = summary || ""
        dlg.open()
    }

    ColumnLayout {
        width: dlg.contentWidth
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
            visible: text.length > 0
            text: dlg.planSummary
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.secondary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
            wrapMode: Text.WordWrap
        }

        Fluent.Separator { Layout.fillWidth: true }

        Text {
            text: "提交标题"
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
        }

        Text {
            Layout.fillWidth: true
            text: dlg.planTitle
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.bodyLarge
            font.bold: true
            wrapMode: Text.WordWrap
        }

        Text {
            text: "提交正文"
            visible: dlg.planBody.length > 0
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
        }

        Text {
            Layout.fillWidth: true
            text: dlg.planBody
            visible: text.length > 0
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.secondary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
            wrapMode: Text.WordWrap
        }
    }
}
