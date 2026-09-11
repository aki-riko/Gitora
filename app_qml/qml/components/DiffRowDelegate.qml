// DiffViewer 虚拟化窗口中的单行渲染
// 由 DiffViewer 的 delegate 池复用:滚动时只重绑属性,禁止在此加动画/定时器/常驻连接。
import QtQuick
import PrismQML as Fluent

Rectangle {
    id: rowItem

    // viewer: DiffViewer 宿主;vr: 统一视图=模型行,分栏视图={k,l,r}
    property var viewer: null
    property var vr: null

    readonly property bool _splitMode: viewer !== null && viewer.displayMode === "split"
    readonly property bool _isUnified: !_splitMode
    readonly property bool _isWrapper: vr !== null && vr.k !== undefined
    readonly property bool _splitRow: _splitMode && _isWrapper && vr.k !== "full"
    readonly property bool _splitFull: _splitMode && _isWrapper && vr.k === "full"
    readonly property var _u: !_splitMode ? vr : null
    readonly property real _w: viewer ? viewer.lineNoWidth : 32
    readonly property real _halfW: Math.max(0, Math.floor((width - 2 * _w) / 2))
    readonly property int _rowH: viewer ? viewer.rowHeight : 18
    readonly property real _pad: viewer ? viewer.contentHorizontalPadding : 4

    // 行背景:内容行按 add/del,块头/文件头为淡色带(GitHub 风格分区)
    function _rowBandColor(row) {
        if (!rowItem.viewer || !row) return "transparent"
        var t = row.t
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

    component SideZone: Item {
        property var row: null
        width: rowItem._halfW
        height: rowItem._rowH
        Rectangle {
            anchors.fill: parent
            color: rowItem._rowBandColor(parent.row)
        }
        Text {
            anchors.fill: parent
            anchors.leftMargin: rowItem._pad
            verticalAlignment: Text.AlignVCenter
            text: rowItem.viewer ? rowItem.viewer.rowHtml(parent.row) : ""
            color: rowItem.viewer ? rowItem.viewer.rowTextDefaultColor(parent.row) : "#000000"
            font.family: "Consolas, Cascadia Code, monospace"
            font.pixelSize: 13
            textFormat: Text.RichText
            wrapMode: Text.NoWrap
        }
    }

    // ── 统一视图: [旧行号][新行号][文本] ──
    Row {
        anchors.fill: parent
        visible: rowItem._isUnified

        NumCell { value: rowItem._u && rowItem._u.o >= 0 ? String(rowItem._u.o) : "" }
        NumCell { value: rowItem._u && rowItem._u.n >= 0 ? String(rowItem._u.n) : "" }
        SideZone {
            row: rowItem._u
            width: Math.max(0, rowItem.width - 2 * rowItem._w)
        }
    }

    // ── 分栏视图: [旧行号][左文本][新行号][右文本] ──
    Row {
        anchors.fill: parent
        visible: rowItem._splitRow

        NumCell {
            value: rowItem.vr && rowItem.vr.l && rowItem.vr.l.o >= 0
                ? String(rowItem.vr.l.o) : ""
        }
        SideZone { row: rowItem.vr ? rowItem.vr.l : null }
        NumCell {
            value: {
                var v = rowItem.vr
                if (!v) return ""
                var side = v.r !== null && v.r !== undefined ? v.r : v.l
                return side && side.n >= 0 ? String(side.n) : ""
            }
        }
        SideZone { row: rowItem.vr ? rowItem.vr.r : null }
    }

    // ── 分栏视图的整行(文件头/块头/元信息): 跨全宽,带分区底色 ──
    Row {
        anchors.fill: parent
        visible: rowItem._splitFull

        Item {
            width: rowItem.width
            height: rowItem._rowH
            Rectangle {
                anchors.fill: parent
                color: rowItem._rowBandColor(rowItem.vr ? rowItem.vr.l : null)
            }
            Text {
                anchors.fill: parent
                anchors.leftMargin: rowItem._pad
                verticalAlignment: Text.AlignVCenter
                text: rowItem.viewer && rowItem.vr && rowItem.vr.l
                    ? rowItem.viewer.rowHtml(rowItem.vr.l) : ""
                color: rowItem.viewer && rowItem.vr && rowItem.vr.l
                    ? rowItem.viewer.rowTextDefaultColor(rowItem.vr.l) : "#888888"
                font.family: "Consolas, Cascadia Code, monospace"
                font.pixelSize: 13
                textFormat: Text.RichText
                wrapMode: Text.NoWrap
            }
        }
    }
}
