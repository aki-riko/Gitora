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
            dlg.lineRows = lines || []
            dlg.loading = false
            dlg.truncated = !!isTruncated
        }
    }

    function _lineColor(line) {
        if (line.indexOf("<<<<<<<") === 0) return Fluent.Enums.accentColor
        if (line.indexOf("=======") === 0) return Fluent.Enums.statusLevel.warningColor
        if (line.indexOf(">>>>>>>") === 0) return Fluent.Enums.statusLevel.successColor
        return Fluent.Enums.textColor.primary
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
                delegate: Text {
                    width: ListView.view ? ListView.view.width : 0
                    height: lineList.itemHeight
                    text: modelData
                    color: dlg._lineColor(modelData)
                    font.family: "Consolas, monospace"
                    font.pixelSize: Fluent.Enums.typography.caption
                    textFormat: Text.PlainText
                    wrapMode: Text.NoWrap
                    verticalAlignment: Text.AlignVCenter
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
