// 编辑仓库根目录下的 Git 规则文件。
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.Card {
    id: root

    property string fileName: ""
    property string _savedContent: ""
    property var scrollPassthroughTarget: null
    readonly property bool dirty: editor.text !== root._savedContent
    signal saveRequested(string content)

    height: editorLayout.implicitHeight + Fluent.Enums.spacing.l * 2

    function loadContent(value) {
        root._savedContent = value || ""
        editor.text = root._savedContent
    }

    function markSaved() {
        root._savedContent = editor.text
    }

    function _routeUnfocusedWheel(wheel) {
        if (!root.scrollPassthroughTarget
                || typeof root.scrollPassthroughTarget.smoothScrollBy !== "function") {
            wheel.accepted = false
            return
        }
        var delta = -wheel.angleDelta.y / 120
            * root.scrollPassthroughTarget.scrollStep
        root.scrollPassthroughTarget.smoothScrollBy(delta)
        wheel.accepted = true
    }

    ColumnLayout {
        id: editorLayout
        anchors.fill: parent
        spacing: Fluent.Enums.spacing.m

        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.s

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
                font.bold: true
            }

            Text {
                text: root.dirty ? "有未保存修改" : "已同步"
                color: root.dirty
                    ? Fluent.Enums.statusLevel.warningColor
                    : Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }
        }

        Fluent.TextEdit {
            id: editor
            Layout.fillWidth: true
            Layout.preferredHeight: 220
            multilineType: Fluent.Enums.input.multiline_plain
            textFormat: TextEdit.PlainText
            wrapMode: TextEdit.NoWrap
            showScrollIndicator: true
            placeholderText: "文件不存在时，保存会创建它"

            MouseArea {
                anchors.fill: parent
                z: Fluent.Enums.zIndex.inputControls
                enabled: !editor.focused
                    && root.scrollPassthroughTarget !== null
                acceptedButtons: Qt.NoButton
                onWheel: (wheel) => root._routeUnfocusedWheel(wheel)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.s

            Text {
                Layout.fillWidth: true
                text: "保存后会作为当前仓库的工作区改动"
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideRight
            }

            Fluent.Button {
                text: "保存"
                icon: Fluent.Enums.icon.save
                style: Fluent.Enums.button.style_primary
                enabled: root.dirty && !!GitBridge && !!GitBridge.repoPath
                onClicked: root.saveRequested(editor.text)
            }
        }
    }
}
