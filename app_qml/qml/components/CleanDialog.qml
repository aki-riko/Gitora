// 清理未跟踪文件对话框(阶段 4:迁移 clean_dialog.py)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "清理未跟踪文件"
    confirmText: "清理"
    cancelText: "取消"

    signal cleanRequested(bool includeDirectories)
    ListModel { id: previewModel }

    function refresh() {
        previewModel.clear()
        if (!GitBridge || !GitBridge.repoPath) return
        GitBridge.requestCleanPreview()  // 异步,结果经 cleanPreviewReady 回传
    }

    Connections {
        target: GitBridge
        function onCleanPreviewReady(files) {
            previewModel.clear()
            for (var i = 0; i < files.length; i++) previewModel.append({ "path": files[i] })
        }
    }

    function openClean() {
        refresh()
        dlg.open()
    }

    function validate() { return previewModel.count > 0 }

    onAccepted: dlg.cleanRequested(includeDirCheck.checked)

    ColumnLayout {
        width: 400
        spacing: Fluent.Enums.spacing.m

        Text {
            Layout.fillWidth: true
            text: "以下未跟踪文件将被永久删除(不可恢复):"
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

        ListView {
            id: previewList
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(previewModel.count * 24 + 8, 200)
            clip: true
            model: previewModel
            delegate: Text {
                width: previewList.width
                text: model.path
                color: Fluent.Enums.textColor.secondary
                font.family: "Consolas, monospace"
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideMiddle
            }
        }

        Text {
            Layout.fillWidth: true
            visible: previewModel.count === 0
            text: "没有可清理的未跟踪文件"
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
        }
    }
}
