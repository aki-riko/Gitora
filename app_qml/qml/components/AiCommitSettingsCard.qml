import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.SettingsCardGroup {
    id: root
    title: "AI 提交规划"

    property bool _loading: false
    property var _providerValues: ["ollama", "openai_responses"]
    property var _scopeValues: ["staged", "all"]

    Component.onCompleted: root.loadSettings()

    Connections {
        target: AiCommitBridge
        function onSettingsChanged() { root.loadSettings() }
        function onConnectionTestFinished(ok, message) {
            if (ok)
                Fluent.NotificationManager.toast.success(root, "连接检测", message)
            else
                Fluent.NotificationManager.toast.error(root, "连接失败", message)
        }
        function onErrorOccurred(message) {
            Fluent.NotificationManager.toast.error(root, "AI 提交规划", message)
        }
    }

    Rectangle {
        width: parent ? parent.width : 0
        height: aiLayout.implicitHeight + Fluent.Enums.spacing.l * 2
        radius: Fluent.Enums.radius.medium
        color: Fluent.Enums.stateColor.settingCardBg
        border.color: Fluent.Enums.stateColor.settingCardBorder
        border.width: Fluent.Enums.border.normal

        ColumnLayout {
            id: aiLayout
            anchors.fill: parent
            anchors.margins: Fluent.Enums.spacing.l
            spacing: Fluent.Enums.spacing.m

            RowLayout {
                Layout.fillWidth: true
                Fluent.Icon {
                    icon: Fluent.Enums.icon.code
                    size: 24
                    color: Fluent.Enums.textColor.secondary
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Fluent.Enums.spacing.xxs
                    Text {
                        text: "模型只生成建议，不会自动提交或推送"
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.body
                        font.bold: true
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "仅本机回环 Ollama 直接发送；非本机 Ollama 与远程 API 每次发送前都会确认范围。"
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                        wrapMode: Text.WordWrap
                    }
                }
                Fluent.CheckBox {
                    id: enabledCheck
                    text: "启用"
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: root.width < 760 ? 1 : 2
                columnSpacing: Fluent.Enums.spacing.m
                rowSpacing: Fluent.Enums.spacing.s

                Fluent.ComboBox {
                    id: providerCombo
                    Layout.fillWidth: true
                    model: ["本地 Ollama", "远程 Responses API"]
                    currentIndex: 0
                }

                Fluent.ComboBox {
                    id: scopeCombo
                    Layout.fillWidth: true
                    model: ["提交规划：仅已暂存差异", "提交规划：全部工作区改动"]
                    currentIndex: 0
                }

                Fluent.LineEdit {
                    id: localEndpointInput
                    Layout.fillWidth: true
                    visible: providerCombo.currentIndex === 0
                    placeholderText: "Ollama 服务地址"
                }
                Fluent.LineEdit {
                    id: localModelInput
                    Layout.fillWidth: true
                    visible: providerCombo.currentIndex === 0
                    placeholderText: "本地模型名"
                }

                Fluent.LineEdit {
                    id: remoteEndpointInput
                    Layout.fillWidth: true
                    visible: providerCombo.currentIndex === 1
                    placeholderText: "Responses API 完整 HTTPS 地址"
                }
                Fluent.LineEdit {
                    id: remoteModelInput
                    Layout.fillWidth: true
                    visible: providerCombo.currentIndex === 1
                    placeholderText: "远程模型名"
                }

                Fluent.LineEdit {
                    id: apiKeyEnvInput
                    Layout.fillWidth: true
                    visible: providerCombo.currentIndex === 1
                    placeholderText: "密钥环境变量名"
                }
                Fluent.LineEdit {
                    id: apiKeyInput
                    Layout.fillWidth: true
                    visible: providerCombo.currentIndex === 1
                    inputType: Fluent.Enums.input.type_password
                    placeholderText: "API 密钥（保存到系统凭据库）"
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Fluent.Enums.spacing.m

                Fluent.CheckBox {
                    id: bodyCheck
                    text: "生成提交正文"
                }
                Text {
                    Layout.fillWidth: true
                    visible: providerCombo.currentIndex === 1
                    text: {
                        if (!AiCommitBridge) return ""
                        if (AiCommitBridge.hasStoredApiKey) return "已保存到系统凭据库"
                        var settings = AiCommitBridge.getSettings()
                        if (settings.hasEnvironmentApiKey) return "已检测到环境变量密钥"
                        if (!settings.credentialStoreAvailable)
                            return settings.credentialStoreError || "系统凭据库不可用"
                        return "未保存远程密钥"
                    }
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    horizontalAlignment: Text.AlignRight
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Fluent.Enums.spacing.s
                Fluent.Button {
                    text: "删除系统凭据"
                    visible: providerCombo.currentIndex === 1 && AiCommitBridge && AiCommitBridge.hasStoredApiKey
                    style: Fluent.Enums.button.style_transparent
                    onClicked: {
                        var result = AiCommitBridge.deleteStoredApiKey()
                        if (result[0])
                            Fluent.NotificationManager.toast.success(root, "系统凭据", result[1] || "密钥已删除")
                        else
                            Fluent.NotificationManager.toast.error(root, "删除失败", result[1] || "无法删除系统凭据")
                    }
                }
                Item { Layout.fillWidth: true }
                Fluent.Button {
                    text: AiCommitBridge && AiCommitBridge.busy ? "检测中…" : "检测连接"
                    enabled: AiCommitBridge && !AiCommitBridge.busy
                    onClicked: {
                        if (root.saveSettings(false)) AiCommitBridge.testConnection()
                    }
                }
                Fluent.Button {
                    text: "保存"
                    style: Fluent.Enums.button.style_primary
                    onClicked: root.saveSettings(true)
                }
            }
        }
    }

    function loadSettings() {
        if (!AiCommitBridge || root._loading) return
        root._loading = true
        var settings = AiCommitBridge.getSettings()
        enabledCheck.checked = settings.enabled
        var providerIndex = root._providerValues.indexOf(settings.provider)
        providerCombo.currentIndex = providerIndex >= 0 ? providerIndex : 0
        localEndpointInput.text = settings.localEndpoint || ""
        localModelInput.text = settings.localModel || ""
        remoteEndpointInput.text = settings.remoteEndpoint || ""
        remoteModelInput.text = settings.remoteModel || ""
        apiKeyEnvInput.text = settings.apiKeyEnv || ""
        bodyCheck.checked = settings.generateBody
        var scopeIndex = root._scopeValues.indexOf(settings.remoteScope)
        scopeCombo.currentIndex = scopeIndex >= 0 ? scopeIndex : 0
        root._loading = false
    }

    function saveSettings(showToast) {
        if (!AiCommitBridge) return false
        var result = AiCommitBridge.saveSettings(
            enabledCheck.checked,
            root._providerValues[providerCombo.currentIndex],
            localEndpointInput.text.trim(),
            localModelInput.text.trim(),
            remoteEndpointInput.text.trim(),
            remoteModelInput.text.trim(),
            apiKeyEnvInput.text.trim(),
            bodyCheck.checked,
            root._scopeValues[scopeCombo.currentIndex]
        )
        if (!result[0]) {
            Fluent.NotificationManager.toast.error(root, "保存失败", result[1] || "")
            return false
        }
        var successMessage = result[1] || "AI 提交规划设置已保存"
        var credentialResult = root.saveCredentialInput()
        if (!credentialResult[0]) {
            Fluent.NotificationManager.toast.error(root, "密钥保存失败", credentialResult[1] || "")
            return false
        }
        if (credentialResult[1])
            successMessage = credentialResult[1]
        if (showToast)
            Fluent.NotificationManager.toast.success(root, "设置已保存", successMessage)
        return true
    }

    function saveCredentialInput() {
        if (apiKeyInput.text.length === 0) return [true, ""]
        var result = AiCommitBridge.storeApiKey(apiKeyInput.text)
        if (result[0]) apiKeyInput.text = ""
        return result
    }
}
