// 远程仓库管理面板:列出所有远程,支持添加 / 修改抓取与推送 URL / 删除。
// 数据源 GitBridge.getRemoteInfo() 的 PrismQML TaskHandle；增删改后异步刷新。
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
        dlg._remotes = []
        remoteModel.clear()
        var task = GitBridge.getRemoteInfo()
        task.succeeded.connect(function(remotes) {
            dlg._remotes = remotes || []
            remoteModel.clear()
            for (var i = 0; i < dlg._remotes.length; i++) {
                var remote = dlg._remotes[i]
                var fetchUrl = remote.fetchUrl || remote.url
                var pushUrl = remote.pushUrl || fetchUrl
                remoteModel.append({
                    "rName": remote.name,
                    "rFetchUrl": fetchUrl,
                    "rPushUrl": pushUrl
                })
            }
        })
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

        // 远程列表:每项 name + fetch/push URL + 修改/删除
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
                        text: "抓取: " + model.rFetchUrl
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    Text {
                        text: "推送: " + model.rPushUrl
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
                        editFetchUrlInput.text = model.rFetchUrl
                        editPushUrlInput.text = model.rPushUrl
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
                var name = addNameInput.text
                var url = addUrlInput.text
                var task = GitBridge.addRemote(name, url)
                task.succeeded.connect(function(result) {
                    if (!result || !result[0]) return
                    dlg.remoteRequested(name, url)
                    addNameInput.text = ""; addUrlInput.text = ""
                    dlg.refresh()
                })
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
            var name = dlg._pendingDelete
            var task = GitBridge.removeRemote(name)
            task.succeeded.connect(function(result) {
                if (result && result[0]) dlg.refresh()
            })
            dlg._pendingDelete = ""
        }
    }

    // 修改远程抓取/推送 URL
    Fluent.MessageBox {
        id: editRemoteBox
        title: ""
        confirmText: "保存"
        cancelText: "取消"
        onAccepted: {
            var name = dlg._editTarget
            var fetchUrl = editFetchUrlInput.text.trim()
            var pushUrl = editPushUrlInput.text.trim()
            var task = GitBridge.setRemoteUrls(name, fetchUrl, pushUrl)
            task.succeeded.connect(function(result) {
                if (result && result[0]) dlg.refresh()
            })
        }
        ColumnLayout {
            width: 400
            spacing: Fluent.Enums.spacing.s
            DialogTitle {
                objectName: "editRemoteDialogTitle"
                text: "修改远程 URL"
            }
            Fluent.LineEdit {
                id: editNameInput
                Layout.fillWidth: true
                enabled: false   // 远程名不可改,改名等于删旧建新
            }
            Fluent.LineEdit {
                id: editFetchUrlInput
                Layout.fillWidth: true
                placeholderText: "抓取 URL"
            }
            Text {
                text: "推送 URL(留空则跟随抓取 URL)"
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }
            Fluent.LineEdit {
                id: editPushUrlInput
                Layout.fillWidth: true
                placeholderText: "推送 URL"
            }
        }
    }

    // 重命名远程
    Fluent.MessageBox {
        id: renameRemoteBox
        title: ""
        confirmText: "保存"
        cancelText: "取消"
        function validate() { return renameRemoteInput.text.trim().length > 0 }
        onAccepted: {
            var oldName = dlg._renameTarget
            var newName = renameRemoteInput.text
            var task = GitBridge.renameRemote(oldName, newName)
            task.succeeded.connect(function(result) {
                if (result && result[0]) dlg.refresh()
            })
            dlg._renameTarget = ""
            renameRemoteInput.text = ""
        }
        ColumnLayout {
            width: 320
            spacing: Fluent.Enums.spacing.m
            DialogTitle {
                objectName: "renameRemoteDialogTitle"
                text: "重命名远程"
            }
            Fluent.LineEdit {
                id: renameRemoteInput
                Layout.fillWidth: true
                placeholderText: "新的远程名称"
            }
        }
    }
}
