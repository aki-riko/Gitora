import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.SettingsCardGroup {
    id: root
    objectName: "aiCommitSettingsCard"
    title: "AI 提交规划"

    property bool _loading: false
    property bool _hasEnvironmentApiKey: false
    property bool _credentialStoreAvailable: true
    property string _credentialStoreError: ""
    property string _modelFetchProvider: ""
    property string _modelFetchEndpoint: ""
    property var _providerValues: ["ollama", "openai_responses", "anthropic"]
    readonly property bool _compactFields: root.width < 760

    Component.onCompleted: root.loadSettings()

    Connections {
        target: AiCommitBridge
        function onSettingsChanged() { root.loadSettings() }
        function onModelListFinished(provider, ok, models, message) {
            if (provider !== root._modelFetchProvider) return
            var matchesCurrentConnection = provider === root._providerValues[
                connectionSection.providerIndex
            ] && connectionSection.activeEndpoint.trim() === root._modelFetchEndpoint
            root.clearModelFetchState()
            if (!matchesCurrentConnection) return
            if (ok) {
                connectionSection.setAvailableModels(provider, models)
            }
        }
        function onBusyChanged() {
            if (!AiCommitBridge.busy && root._modelFetchProvider.length > 0)
                root.clearModelFetchState()
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
                spacing: Fluent.Enums.spacing.m

                Fluent.Icon {
                    icon: Fluent.Enums.icon.code
                    size: 24
                    color: Fluent.Enums.textColor.secondary
                    Layout.alignment: Qt.AlignTop
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Fluent.Enums.spacing.xxs

                    Text {
                        Layout.fillWidth: true
                        text: "让模型整理整个工作区，一次确认即可提交推送"
                        textFormat: Text.PlainText
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.body
                        font.bold: true
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "生成方案后，只有点击“采用并提交推送”才会执行 Git 写操作。"
                        textFormat: Text.PlainText
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                        wrapMode: Text.WordWrap
                    }
                }

                Fluent.ToggleSwitch {
                    id: enabledSwitch
                    text: "启用 AI 提交"
                    Layout.alignment: Qt.AlignTop
                }
            }

            RowLayout {
                id: settingsActions
                objectName: "aiSettingsActions"
                Layout.fillWidth: true
                spacing: Fluent.Enums.spacing.s

                Text {
                    Layout.fillWidth: true
                    text: enabledSwitch.checked
                        ? "保存后可在提交下拉菜单使用 AI 提交"
                        : "AI 提交当前未启用"
                    textFormat: Text.PlainText
                    color: Fluent.Enums.textColor.tertiary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    elide: Text.ElideRight
                }

                Fluent.Button {
                    objectName: "aiConnectionTestButton"
                    text: AiCommitBridge && AiCommitBridge.busy ? "检测中…" : "检测连接"
                    enabled: AiCommitBridge && !AiCommitBridge.busy
                    onClicked: {
                        if (root.saveSettings(false)) AiCommitBridge.testConnection()
                    }
                }

                Fluent.Button {
                    objectName: "aiSettingsSaveButton"
                    text: "保存设置"
                    icon: Fluent.Enums.icon.save
                    style: Fluent.Enums.button.style_primary
                    onClicked: root.saveSettings(true)
                }
            }

            Fluent.Separator { Layout.fillWidth: true }

            AiCommitConnectionSection {
                id: connectionSection
                objectName: "aiConnectionSection"
                Layout.fillWidth: true
                compact: root._compactFields
                hasStoredApiKey: Boolean(
                    AiCommitBridge && AiCommitBridge.hasStoredApiKey
                )
                credentialStatusText: root.credentialStatusText()
                credentialStatusColor: root.credentialStatusColor()
                modelsLoading: root._modelFetchProvider.length > 0
                modelFetchEnabled: Boolean(
                    AiCommitBridge && !AiCommitBridge.busy
                )
                onDeleteCredentialRequested: root.deleteStoredCredential()
                onFetchModelsRequested: root.fetchModels()
            }

            Fluent.Separator { Layout.fillWidth: true }

            AiCommitRulesSection {
                id: rulesSection
                Layout.fillWidth: true
                compact: root._compactFields
            }
        }
    }

    function credentialStatusText() {
        if (!AiCommitBridge) return ""
        if (AiCommitBridge.hasStoredApiKey) return "已安全保存到系统凭据库"
        if (root._hasEnvironmentApiKey) return "将使用环境变量中的密钥"
        if (!root._credentialStoreAvailable)
            return root._credentialStoreError || "系统凭据库不可用"
        return "尚未保存 API 密钥"
    }

    function credentialStatusColor() {
        if (AiCommitBridge && AiCommitBridge.hasStoredApiKey)
            return Fluent.Enums.statusLevel.getColor(Fluent.Enums.statusLevel.successStr)
        if (!root._credentialStoreAvailable)
            return Fluent.Enums.statusLevel.getColor(Fluent.Enums.statusLevel.errorStr)
        if (root._hasEnvironmentApiKey)
            return Fluent.Enums.statusLevel.getColor(Fluent.Enums.statusLevel.infoStr)
        return Fluent.Enums.textColor.tertiary
    }

    function deleteStoredCredential() {
        var result = AiCommitBridge.deleteStoredApiKey()
        if (result[0])
            Fluent.NotificationManager.desktop.success("系统凭据", result[1] || "密钥已删除")
        else
            Fluent.NotificationManager.desktop.error("删除失败", result[1] || "无法删除系统凭据")
    }

    function fetchModels() {
        if (!AiCommitBridge || !root.saveSettings(false)) return
        root._modelFetchProvider = root._providerValues[connectionSection.providerIndex]
        root._modelFetchEndpoint = connectionSection.activeEndpoint.trim()
        AiCommitBridge.fetchModels()
    }

    function clearModelFetchState() {
        root._modelFetchProvider = ""
        root._modelFetchEndpoint = ""
    }

    function loadSettings() {
        if (!AiCommitBridge || root._loading) return
        root._loading = true
        var settings = AiCommitBridge.getSettings()
        enabledSwitch.checked = settings.enabled
        var providerIndex = root._providerValues.indexOf(settings.provider)
        connectionSection.providerIndex = providerIndex >= 0 ? providerIndex : 0
        connectionSection.localEndpoint = settings.localEndpoint || ""
        connectionSection.localModel = settings.localModel || ""
        connectionSection.remoteEndpoint = settings.remoteEndpoint || ""
        connectionSection.remoteModel = settings.remoteModel || ""
        connectionSection.apiKeyEnvironment = settings.apiKeyEnv || ""
        rulesSection.generateBody = settings.generateBody
        root._hasEnvironmentApiKey = settings.hasEnvironmentApiKey || false
        root._credentialStoreAvailable = settings.credentialStoreAvailable !== false
        root._credentialStoreError = settings.credentialStoreError || ""
        root._loading = false
    }

    function saveSettings(showToast) {
        if (!AiCommitBridge) return false
        var currentSettings = AiCommitBridge.getSettings()
        var result = AiCommitBridge.saveSettings(
            enabledSwitch.checked,
            root._providerValues[connectionSection.providerIndex],
            connectionSection.localEndpoint.trim(),
            connectionSection.localModel.trim(),
            connectionSection.remoteEndpoint.trim(),
            connectionSection.remoteModel.trim(),
            connectionSection.apiKeyEnvironment.trim(),
            rulesSection.generateBody,
            currentSettings.remoteScope
        )
        if (!result[0]) {
            Fluent.NotificationManager.desktop.error("保存失败", result[1] || "")
            return false
        }
        var successMessage = result[1] || "AI 提交规划设置已保存"
        var credentialResult = root.saveCredentialInput()
        if (!credentialResult[0]) {
            Fluent.NotificationManager.desktop.error("密钥保存失败", credentialResult[1] || "")
            return false
        }
        if (credentialResult[1])
            successMessage = credentialResult[1]
        if (showToast)
            Fluent.NotificationManager.desktop.success("设置已保存", successMessage)
        return true
    }

    function saveCredentialInput() {
        if (connectionSection.credentialInput.length === 0) return [true, ""]
        var result = AiCommitBridge.storeApiKey(connectionSection.credentialInput)
        if (result[0]) connectionSection.credentialInput = ""
        return result
    }
}
