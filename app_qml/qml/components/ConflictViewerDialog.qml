// 冲突内容查看对话框(阶段 5:迁移 conflict_viewer_dialog.py)
// 只读展示冲突文件内容,对冲突标记行高亮:
//   <<<<<<< 蓝(我们的)  ======= 橙(分隔)  >>>>>>> 绿(他们的)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg
    property string _displayTitle: "冲突内容"
    property string _requestRepoPath: ""
    property string _requestPath: ""
    property bool loading: false
    property bool truncated: false
    property var lineRows: []
    title: ""
    confirmText: "关闭"
    cancelButtonVisible: false

    function openFor(path) {
        dlg._displayTitle = "冲突内容 - " + path
        dlg.lineRows = []
        dlg._requestRepoPath = GitBridge && GitBridge.repoPath
            ? GitBridge.repoPath : ""
        dlg._requestPath = path
        dlg.loading = true
        dlg.truncated = false
        GitBridge.requestConflictFile(path)
        dlg.open()
    }

    function _decorateLines(lines) {
        var rows = []
        var region = "normal"
        var sourceLines = lines || []
        for (var i = 0; i < sourceLines.length; i++) {
            var line = String(sourceLines[i])
            var kind = region
            if (line.indexOf("<<<<<<<") === 0) {
                kind = "oursMarker"
                region = "ours"
            } else if (line.indexOf("=======") === 0) {
                kind = "separator"
                region = "theirs"
            } else if (line.indexOf(">>>>>>>") === 0) {
                kind = "theirsMarker"
                region = "normal"
            }
            rows.push({text: line, kind: kind})
        }
        return rows
    }

    Connections {
        target: GitBridge
        function onRepoPathChanged(path) {
            dlg._requestRepoPath = ""
            dlg._requestPath = ""
            dlg.loading = false
            dlg.truncated = false
            dlg.lineRows = []
        }
        function onConflictFileReady(repoPath, path, lines, isTruncated) {
            if (!GitBridge || repoPath !== GitBridge.repoPath
                    || repoPath !== dlg._requestRepoPath || path !== dlg._requestPath)
                return
            dlg.lineRows = dlg._decorateLines(lines)
            dlg.loading = false
            dlg.truncated = !!isTruncated
        }
    }

    function _lineColor(row) {
        if (!row || row.kind === "normal") return Fluent.Enums.textColor.primary
        if (row.kind === "ours" || row.kind === "oursMarker") return Fluent.Enums.accentColor
        if (row.kind === "separator") return Fluent.Enums.statusLevel.warningColor
        if (row.kind === "theirs" || row.kind === "theirsMarker") return Fluent.Enums.statusLevel.successColor
        return Fluent.Enums.textColor.primary
    }

    function _lineBackground(row) {
        if (!row || row.kind === "normal") return "transparent"
        if (row.kind === "ours" || row.kind === "oursMarker") {
            return Qt.rgba(Fluent.Enums.accentColor.r, Fluent.Enums.accentColor.g,
                           Fluent.Enums.accentColor.b, row.kind === "oursMarker" ? 0.2 : 0.08)
        }
        if (row.kind === "separator") {
            return Qt.rgba(Fluent.Enums.statusLevel.warningColor.r,
                           Fluent.Enums.statusLevel.warningColor.g,
                           Fluent.Enums.statusLevel.warningColor.b, 0.2)
        }
        return Qt.rgba(Fluent.Enums.statusLevel.successColor.r,
                       Fluent.Enums.statusLevel.successColor.g,
                       Fluent.Enums.statusLevel.successColor.b,
                       row.kind === "theirsMarker" ? 0.2 : 0.08)
    }

    function _lineMarkerColor(row) {
        if (!row || row.kind === "normal") return "transparent"
        return _lineColor(row)
    }

    ColumnLayout {
        width: 600
        spacing: Fluent.Enums.spacing.m

        DialogTitle {
            objectName: "conflictViewerDialogTitle"
            text: dlg._displayTitle + (dlg.truncated ? "（内容已截断）" : "")
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 420
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border

            Fluent.ScrollArea {
                id: lineList
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                type: Fluent.Enums.scroll.type_list
                itemHeight: Fluent.Enums.typography.caption + Fluent.Enums.spacing.m
                reuseItems: true
                bounceEnabled: false
                padding: 0
                model: dlg.lineRows
                delegate: Rectangle {
                    width: ListView.view ? ListView.view.width : 0
                    height: lineList.itemHeight
                    color: dlg._lineBackground(modelData)

                    Rectangle {
                        anchors.left: parent.left
                        anchors.top: parent.top
                        anchors.bottom: parent.bottom
                        width: 3
                        color: dlg._lineMarkerColor(modelData)
                    }

                    Text {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        text: modelData.text
                        color: dlg._lineColor(modelData)
                        font.family: "Consolas, monospace"
                        font.pixelSize: Fluent.Enums.typography.caption
                        textFormat: Text.PlainText
                        wrapMode: Text.NoWrap
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
            Text {
                anchors.centerIn: parent
                visible: dlg.loading
                text: "正在读取..."
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
            }
        }
    }
}
