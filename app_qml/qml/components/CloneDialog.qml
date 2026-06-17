// 克隆仓库对话框(阶段 4:迁移 clone_dialog.py)
// 用法:CloneDialog { onCloneRequested: (url, path) => GitBridge.clone(url, path) }; dlg.open()
import QtQuick
import QtQuick.Layouts
import QtQuick.Dialogs

import FluentQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "克隆仓库"
    confirmText: "克隆"
    cancelText: "取消"

    signal cloneRequested(string url, string path)

    function validate() {
        return urlInput.text.length > 0 && pathInput.text.length > 0
    }

    onAccepted: dlg.cloneRequested(urlInput.text, pathInput.text)

    ColumnLayout {
        width: 380
        spacing: Fluent.Enums.spacing.m

        Fluent.LineEdit {
            id: urlInput
            Layout.fillWidth: true
            placeholderText: "仓库 URL (https:// 或 git@...)"
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: Fluent.Enums.spacing.s
            Fluent.LineEdit {
                id: pathInput
                Layout.fillWidth: true
                placeholderText: "本地目录"
            }
            Fluent.Button {
                text: "浏览"
                onClicked: pathPicker.open()
            }
        }
    }

    FolderDialog {
        id: pathPicker
        title: "选择克隆目标目录"
        onAccepted: pathInput.text = selectedFolder.toString().replace(/^file:\/\/\//, "")
    }
}
