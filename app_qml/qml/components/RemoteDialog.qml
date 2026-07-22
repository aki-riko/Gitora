// 远程仓库管理面板:列出所有远程,支持添加 / 修改 URL / 删除。
// 数据源 GitBridge.getRemoteInfo() → [{name, url}, ...];增删改后即时刷新列表。
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.DialogBoxCore {
    id: dlg

    // 兼容旧接口:仍暴露 remoteRequested(用于 InitRepoGuide 等直接添加场景)
    signal remoteRequested(string name, string url)

    // 底部关闭按钮(照 CommitDetailDialog 范式)
    footer: Component {
        Row {
            Fluent.ButtonCore {
                text: "关闭"
                style: Fluent.Enums.button.style_primary
                width: Fluent.Enums.dialog.buttonWidth
                height: Fluent.Enums.dialog.buttonHeight
                onClicked: dlg.reject()
            }
        }
    }

    property var _remotes: []
    property string _pendingDelete: ""   // 待删除的远程名
    property string _editTarget: ""      // 待修改 URL 的远程名
    property string _renameTarget: ""    // 待重命名的远程名

    // 载入远程列表(打开面板时调用)
    function refresh() {
        dlg._remotes = GitBridge.getRemoteInfo()
        remoteModel.clear()
        for (var i = 0; i < dlg._remotes.length; i++)
            remoteModel.append({ "rName": dlg._remotes[i].name, "rUrl": dlg._remotes[i].url })
    }

    // 刷新列表并打开面板(不覆盖基类 open,避免遮蔽其弹出定位逻辑)
    function openPanel() {
        refresh()
        dlg.open()
    }

    ListModel { id: remoteModel }

    ColumnLayout {
        width: 460
        spacing: Fluent.Enums.spacing.m

        // 自绘标题(DialogBoxCore 无内置 title,避免像 MessageBox 那样与内容重叠)
        Text {
            text: "远程管理"
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.subtitle
            font.bold: true
        }

        Text {
            text: remoteModel.count > 0 ? "已配置的远程:" : "暂无远程仓库,可在下方添加"
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
        }

        // 远程列表:每项 name + url + 修改/删除
        Repeater {
            model: remoteModel
            delegate: RowLayout {
                Layout.fillWidth: true
                spacing: Fluent.Enums.spacing.s

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        text: model.rName
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.body
                        font.bold: true
                    }
                    Text {
                        text: model.rUrl
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                }
                Fluent.Button {
                    text: "修改"
                    onClicked: {
                        dlg._editTarget = model.rName
                        editNameInput.text = model.rName
                        editUrlInput.text = model.rUrl
                        editRemoteBox.open()
                    }
                }
                Fluent.Button {
                    text: "重命名"
                    style: Fluent.Enums.button.style_transparent
                    onClicked: {
                        dlg._renameTarget = model.rName
                        renameRemoteInput.text = model.rName
                        renameRemoteBox.open()
                    }
                }
                Fluent.Button {
                    text: "删除"
                    style: Fluent.Enums.button.style_transparent
                    onClicked: {
                        dlg._pendingDelete = model.rName
                        deleteRemoteBox.open()
                    }
                }
            }
        }

        // 分隔 + 添加新远程
        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Fluent.Enums.dividerColor
        }
        Text {
            text: "添加远程:"
            color: Fluent.Enums.textColor.primary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
        }
        Fluent.LineEdit {
            id: addNameInput
            Layout.fillWidth: true
            placeholderText: "名称(如 origin)"
        }
        Fluent.LineEdit {
            id: addUrlInput
            Layout.fillWidth: true
            placeholderText: "URL(如 https://... 或 git@...)"
        }
        Fluent.Button {
            text: "添加"
            style: Fluent.Enums.button.style_primary
            enabled: addNameInput.text.length > 0 && addUrlInput.text.length > 0
            onClicked: {
                var res = GitBridge.addRemote(addNameInput.text, addUrlInput.text)
                if (res[0]) {
                    Fluent.NotificationManager.desktop.success("已添加远程", addNameInput.text)
                    dlg.remoteRequested(addNameInput.text, addUrlInput.text)
                    addNameInput.text = ""; addUrlInput.text = ""
                    dlg.refresh()
                } else {
                    Fluent.NotificationManager.desktop.error("添加失败", res[1] || "")
                }
            }
        }
    }

    // 删除远程确认
    Fluent.MessageBox {
        id: deleteRemoteBox
        title: "删除远程"
        content: "确定删除远程 \"" + dlg._pendingDelete + "\" 吗?此操作只影响本地远程配置,不会删除远端仓库。"
        confirmText: "删除"
        cancelText: "取消"
        onAccepted: {
            var res = GitBridge.removeRemote(dlg._pendingDelete)
            if (res[0]) {
                Fluent.NotificationManager.desktop.success("已删除远程", dlg._pendingDelete)
                dlg.refresh()
            } else {
                Fluent.NotificationManager.desktop.error("删除失败", res[1] || "")
            }
            dlg._pendingDelete = ""
        }
    }

    // 修改远程 URL
    Fluent.MessageBox {
        id: editRemoteBox
        title: "修改远程 URL"
        confirmText: "保存"
        cancelText: "取消"
        onAccepted: {
            var res = GitBridge.setRemoteUrl(dlg._editTarget, editUrlInput.text)
            if (res[0]) {
                Fluent.NotificationManager.desktop.success("已更新 URL", dlg._editTarget)
                dlg.refresh()
            } else {
                Fluent.NotificationManager.desktop.error("更新失败", res[1] || "")
            }
        }
        ColumnLayout {
            width: 400
            spacing: Fluent.Enums.spacing.s
            Fluent.LineEdit {
                id: editNameInput
                Layout.fillWidth: true
                enabled: false   // 远程名不可改,改名等于删旧建新
            }
            Fluent.LineEdit {
                id: editUrlInput
                Layout.fillWidth: true
                placeholderText: "新的远程 URL"
            }
        }
    }

    // 重命名远程
    Fluent.MessageBox {
        id: renameRemoteBox
        title: "重命名远程"
        confirmText: "保存"
        cancelText: "取消"
        function validate() { return renameRemoteInput.text.trim().length > 0 }
        onAccepted: {
            var res = GitBridge.renameRemote(dlg._renameTarget, renameRemoteInput.text)
            if (res[0]) {
                Fluent.NotificationManager.desktop.success("已重命名远程", res[1] || "")
                dlg.refresh()
            } else {
                Fluent.NotificationManager.desktop.error("重命名失败", res[1] || "")
            }
            dlg._renameTarget = ""
            renameRemoteInput.text = ""
        }
        Fluent.LineEdit {
            id: renameRemoteInput
            width: 320
            placeholderText: "新的远程名称"
        }
    }
}
