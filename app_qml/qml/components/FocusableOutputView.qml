// 只读文本输出：获得焦点后滚动自身，未聚焦时把滚轮交给外层页面。
import QtQuick

import PrismQML as Fluent

Item {
    id: root

    property string text: ""
    property var scrollPassthroughTarget: null
    readonly property bool focused: outputText.activeFocus
    readonly property real contentY: outputScrollArea.contentY

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

    Fluent.ScrollArea {
        id: outputScrollArea
        objectName: root.objectName !== "" ? root.objectName + "ScrollArea" : ""
        anchors.fill: parent
        padding: 0

        TextEdit {
            id: outputText
            objectName: root.objectName !== "" ? root.objectName + "Text" : ""
            readOnly: true
            selectByMouse: true
            textFormat: TextEdit.PlainText
            wrapMode: TextEdit.NoWrap
            font.family: "Consolas, monospace"
            font.pixelSize: Fluent.Enums.typography.caption
            color: Fluent.Enums.textColor.primary
            text: root.text
        }
    }

    MouseArea {
        anchors.fill: parent
        z: Fluent.Enums.zIndex.inputControls
        enabled: !outputText.activeFocus
            && root.scrollPassthroughTarget !== null
        // 外层 ScrollArea 按此协议主动调度嵌套滚动，未聚焦时代理给页面。
        readonly property var flickableItem: enabled
            ? outputScrollArea.flickableItem : null

        function smoothScrollBy(delta) {
            root.scrollPassthroughTarget.smoothScrollBy(delta)
        }

        acceptedButtons: Qt.NoButton
        onWheel: (wheel) => root._routeUnfocusedWheel(wheel)
    }
}
