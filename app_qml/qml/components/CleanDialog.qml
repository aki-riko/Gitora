// 清理未跟踪文件对话框(阶段 4:迁移 clean_dialog.py)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: ""
    confirmText: "清理"
    cancelText: "取消"

    signal cleanRequested(bool includeDirectories)
    property string _requestRepoPath: ""
    property int totalCount: 0
    property bool truncated: false
    property var previewRows: []

    function refresh() {
        dlg.previewRows = []
        dlg.totalCount = 0
        dlg.truncated = false
        if (!GitBridge || !GitBridge.repoPath) return
        dlg._requestRepoPath = GitBridge.repoPath
        GitBridge.requestCleanPreview()  // 异步,结果经 cleanPreviewReady 回传
    }

    Connections {
        target: GitBridge
        function onRepoPathChanged(path) {
            dlg._requestRepoPath = ""
            dlg.previewRows = []
            dlg.totalCount = 0
            dlg.truncated = false
        }
        function onCleanPreviewReady(repoPath, files, total, isTruncated) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== dlg._requestRepoPath) return
            dlg.previewRows = files || []
            dlg.totalCount = total || files.length
            dlg.truncated = !!isTruncated
        }
    }

    function openClean() {
        refresh()
        dlg.open()
    }

    function validate() { return dlg.previewRows.length > 0 }

    onAccepted: dlg.cleanRequested(includeDirCheck.checked)

    ColumnLayout {
        width: 400
        spacing: Fluent.Enums.spacing.m

        DialogTitle {
            objectName: "cleanDialogTitle"
            text: "清理未跟踪文件"
        }

        Text {
            Layout.fillWidth: true
            text: "以下未跟踪文件将被永久删除(不可恢复):"
                + (dlg.truncated ? "（仅显示前 " + dlg.previewRows.length + " / " + dlg.totalCount + " 项）" : "")
            color: Fluent.Enums.statusLevel.warningColor
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            wrapMode: Text.WordWrap
        }

        Fluent.CheckBox {
            id: includeDirCheck
            text: "包括未跟踪的目录"
            checked: true
        }

        Fluent.ScrollArea {
            id: previewList
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(dlg.previewRows.length * itemHeight + Fluent.Enums.spacing.m, 200)
            type: Fluent.Enums.scroll.type_list
            itemHeight: Fluent.Enums.typography.caption + Fluent.Enums.spacing.l
            reuseItems: true
            bounceEnabled: false
            padding: 0
            model: dlg.previewRows
            delegate: Text {
                width: ListView.view ? ListView.view.width : 0
                height: previewList.itemHeight
                text: modelData
                color: Fluent.Enums.textColor.secondary
                font.family: "Consolas, monospace"
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideMiddle
                verticalAlignment: Text.AlignVCenter
            }
        }

        Text {
            Layout.fillWidth: true
            visible: dlg.previewRows.length === 0
            text: "没有可清理的未跟踪文件"
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
        }
    }
}
