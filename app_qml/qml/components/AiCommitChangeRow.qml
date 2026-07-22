import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Rectangle {
    id: row

    required property var change
    required property var targetIds
    required property var targetLabels
    required property bool interactionEnabled

    signal moveRequested(string changeId, string targetGroupId)

    enabled: interactionEnabled
    width: parent ? parent.width : 0
    height: changeLayout.implicitHeight + Fluent.Enums.spacing.s * 2
    radius: Fluent.Enums.radius.small
    color: Fluent.Enums.stateColor.hover

    ColumnLayout {
        id: changeLayout
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.s
        spacing: Fluent.Enums.spacing.xs

        Text {
            Layout.fillWidth: true
            text: row.change.path + (row.change.kind === "hunk" ? " · 代码块" : "")
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            elide: Text.ElideMiddle
        }
        Text {
            Layout.fillWidth: true
            visible: row.change.kind === "hunk"
            text: row.change.header
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.secondary
            font.family: "Consolas, Cascadia Code, monospace"
            font.pixelSize: Fluent.Enums.typography.caption
            elide: Text.ElideRight
        }
        Text {
            Layout.fillWidth: true
            visible: row.change.kind === "hunk"
            text: row.change.content
            textFormat: Text.PlainText
            color: Fluent.Enums.textColor.tertiary
            font.family: "Consolas, Cascadia Code, monospace"
            font.pixelSize: Fluent.Enums.typography.caption
            wrapMode: Text.WrapAnywhere
            maximumLineCount: 4
            elide: Text.ElideRight
        }
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: (row.change.staged ? "已暂存" : "未暂存") + " · "
                    + row.change.status + "  +" + row.change.additions
                    + " / -" + row.change.deletions
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }
            Item { Layout.fillWidth: true }
            Fluent.ComboBox {
                Layout.preferredWidth: 160
                model: row.targetLabels
                currentIndex: Math.max(0, row.targetIds.indexOf(row.change.groupId))
                onActivated: function(targetIndex) {
                    row.moveRequested(
                        row.change.changeId, row.targetIds[targetIndex]
                    )
                }
            }
        }
        Text {
            Layout.fillWidth: true
            visible: row.change.unsupportedReason.length > 0
            text: row.change.unsupportedReason
            textFormat: Text.PlainText
            color: Fluent.Enums.statusLevel.warningColor
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            wrapMode: Text.WordWrap
        }
    }
}
