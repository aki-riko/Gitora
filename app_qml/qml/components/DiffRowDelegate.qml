// DiffViewer 虚拟化窗口中的单行渲染(统一视图)
// 由 DiffViewer 的 delegate 池复用:滚动时只重绑属性,禁止在此加动画/定时器/常驻连接。
import QtQuick
import PrismQML as Fluent

Rectangle {
    id: rowItem

    // viewer: DiffViewer 宿主;row: 模型行({t,o,n,x,fi,seg})
    property var viewer: null
    property var row: null

    readonly property var _u: row
    readonly property real _w: viewer ? viewer.lineNoWidth : 32
    readonly property int _rowH: viewer ? viewer.rowHeight : 18
    readonly property real _pad: viewer ? viewer.contentHorizontalPadding : 4

    // 行背景:内容行按 add/del,块头/文件头为淡色带(GitHub 风格分区)
    function _rowBandColor(r) {
        if (!rowItem.viewer || !r) return "transparent"
        var t = r.t
        var c = rowItem.viewer.rowColors
        if (t === "add") return c.addBg
        if (t === "del") return c.delBg
        if (t === "hunk") return c.hunkBg
        if (t === "file") return c.fileBg
        return "transparent"
    }

    color: "transparent"
    height: _rowH

    component NumCell: Item {
        property string value: ""
        width: rowItem._w
        height: rowItem._rowH
        Text {
            anchors.fill: parent
            anchors.rightMargin: 6
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter
            text: parent.value === "" ? "" : parent.value
            color: rowItem.viewer ? rowItem.viewer.rowColors.lineNo : "#888888"
            font.family: "Consolas, Cascadia Code, monospace"
            font.pixelSize: 13
            textFormat: Text.PlainText
        }
    }

    // ── 统一视图: [旧行号][新行号][文本] ──
    Row {
        anchors.fill: parent

        NumCell { value: rowItem._u && rowItem._u.o >= 0 ? String(rowItem._u.o) : "" }
        NumCell { value: rowItem._u && rowItem._u.n >= 0 ? String(rowItem._u.n) : "" }
        Item {
            width: Math.max(0, rowItem.width - 2 * rowItem._w)
            height: rowItem._rowH
            Rectangle {
                anchors.fill: parent
                color: rowItem._rowBandColor(rowItem._u)
            }
            Text {
                anchors.fill: parent
                anchors.leftMargin: rowItem._pad
                verticalAlignment: Text.AlignVCenter
                text: rowItem.viewer ? rowItem.viewer.rowHtml(rowItem._u) : ""
                color: rowItem.viewer ? rowItem.viewer.rowTextDefaultColor(rowItem._u) : "#000000"
                font.family: "Consolas, Cascadia Code, monospace"
                font.pixelSize: 13
                textFormat: Text.RichText
                wrapMode: Text.NoWrap
            }
        }
    }
}
