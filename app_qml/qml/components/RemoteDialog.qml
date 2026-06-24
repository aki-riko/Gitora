// 远程仓库配置对话框(阶段 4:迁移 remote_dialog.py 核心)
// 收集远程名称 + URL。协议拼装向导由 RemoteConfigWizard 承担,此处直接输入完整 URL。
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg
    title: "添加远程仓库"
    confirmText: "添加"
    cancelText: "取消"

    signal remoteRequested(string name, string url)

    function validate() {
        return nameInput.text.length > 0 && urlInput.text.length > 0
    }

    onAccepted: dlg.remoteRequested(nameInput.text, urlInput.text)

    ColumnLayout {
        width: 380
        spacing: Fluent.Enums.spacing.m

        Fluent.LineEdit {
            id: nameInput
            Layout.fillWidth: true
            placeholderText: "远程名称 (如 origin)"
            text: "origin"
        }
        Fluent.LineEdit {
            id: urlInput
            Layout.fillWidth: true
            placeholderText: "远程 URL (https:// 或 git@host:user/repo.git)"
        }
    }
}
