import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

ColumnLayout {
    id: root
    objectName: "aiCommitConnectionSection"

    property bool compact: false
    property bool hasStoredApiKey: false
    property string credentialStatusText: ""
    property color credentialStatusColor: Fluent.Enums.textColor.tertiary
    property alias providerIndex: providerCombo.currentIndex
    property alias localEndpoint: localEndpointInput.text
    property string localModel: ""
    property alias remoteEndpoint: remoteEndpointInput.text
    property string remoteModel: ""
    property alias apiKeyEnvironment: apiKeyEnvInput.text
    property alias credentialInput: apiKeyInput.text
    property var localModels: []
    property var remoteModels: []
    property bool modelsLoading: false
    property bool modelFetchEnabled: false
    property bool _syncingModel: false
    readonly property bool isRemote: providerCombo.currentIndex > 0
    readonly property string activeEndpoint: root.isRemote
        ? remoteEndpointInput.text : localEndpointInput.text
    readonly property bool hasAvailableModels: root.isRemote
        ? root.remoteModels.length > 0 : root.localModels.length > 0

    signal deleteCredentialRequested()
    signal fetchModelsRequested()

    onLocalEndpointChanged: root.resetModelOptions(false)
    onRemoteEndpointChanged: root.resetModelOptions(true)
    onLocalModelChanged: root.ensureConfiguredModel(false)
    onRemoteModelChanged: root.ensureConfiguredModel(true)

    spacing: Fluent.Enums.spacing.s

    Text {
        Layout.fillWidth: true
        text: "模型连接"
        textFormat: Text.PlainText
        color: Fluent.Enums.textColor.primary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.body
        font.bold: true
    }

    Text {
        Layout.fillWidth: true
        text: "选择来源并填写服务地址，然后获取模型列表。"
        textFormat: Text.PlainText
        color: Fluent.Enums.textColor.tertiary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.caption
        wrapMode: Text.WordWrap
    }

    GridLayout {
        id: connectionFields
        Layout.fillWidth: true
        columns: root.compact ? 1 : 2
        columnSpacing: Fluent.Enums.spacing.m
        rowSpacing: Fluent.Enums.spacing.s

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 1
            spacing: Fluent.Enums.spacing.xxs

            Text {
                text: "模型来源"
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }

            Fluent.ComboBox {
                id: providerCombo
                Layout.fillWidth: true
                model: [
                    "本地 Ollama",
                    "远程 OpenAI 兼容 API",
                    "Anthropic Messages API"
                ]
                currentIndex: 0
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 1
            spacing: Fluent.Enums.spacing.xxs

            Text {
                text: "服务地址"
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }

            Fluent.LineEdit {
                id: localEndpointInput
                Layout.fillWidth: true
                visible: !root.isRemote
                placeholderText: "输入 Ollama 服务地址"
            }

            Fluent.LineEdit {
                id: remoteEndpointInput
                Layout.fillWidth: true
                visible: root.isRemote
                placeholderText: "输入 API 基础地址或 Chat/Responses/Messages 完整地址"
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.columnSpan: connectionFields.columns
            Layout.minimumWidth: 0
            spacing: Fluent.Enums.spacing.xxs

            Text {
                text: "模型名称"
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Fluent.Enums.spacing.s

                Fluent.ComboBox {
                    id: localModelCombo
                    objectName: "localModelCombo"
                    Layout.fillWidth: true
                    visible: !root.isRemote
                    model: root.localModels
                    currentIndex: -1
                    placeholderText: "请先获取本地模型"
                    onActivated: function(index) {
                        root.selectModel(false, index)
                    }
                }

                Fluent.ComboBox {
                    id: remoteModelCombo
                    objectName: "remoteModelCombo"
                    Layout.fillWidth: true
                    visible: root.isRemote
                    model: root.remoteModels
                    currentIndex: -1
                    placeholderText: "请先获取远程模型"
                    onActivated: function(index) {
                        root.selectModel(true, index)
                    }
                }

                Fluent.Button {
                    objectName: "fetchModelsButton"
                    text: root.modelsLoading ? "正在获取…"
                        : (root.hasAvailableModels ? "刷新模型" : "获取模型")
                    enabled: root.modelFetchEnabled && !root.modelsLoading
                        && root.activeEndpoint.trim().length > 0
                    onClicked: root.fetchModelsRequested()
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.columnSpan: 1
            Layout.minimumWidth: 0
            Layout.preferredWidth: 1
            visible: root.isRemote
            spacing: Fluent.Enums.spacing.xxs

            Text {
                text: "系统凭据"
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }

            Fluent.LineEdit {
                id: apiKeyInput
                Layout.fillWidth: true
                inputType: Fluent.Enums.input.type_password
                placeholderText: "API 密钥（保存到系统凭据库）"
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 1
            visible: root.isRemote
            spacing: Fluent.Enums.spacing.xxs

            Text {
                text: "环境变量回退（可选）"
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }

            Fluent.LineEdit {
                id: apiKeyEnvInput
                Layout.fillWidth: true
                placeholderText: "环境变量名"
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.columnSpan: connectionFields.columns
            visible: root.isRemote
            spacing: Fluent.Enums.spacing.s

            Rectangle {
                width: 8
                height: 8
                radius: 4
                color: root.credentialStatusColor
                Layout.alignment: Qt.AlignVCenter
            }

            Text {
                Layout.fillWidth: true
                text: root.credentialStatusText
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideRight
            }

            Fluent.Button {
                text: "删除凭据"
                visible: root.hasStoredApiKey
                style: Fluent.Enums.button.style_transparent
                onClicked: root.deleteCredentialRequested()
            }
        }
    }

    function selectModel(remote, index) {
        var values = remote ? root.remoteModels : root.localModels
        if (index < 0 || index >= values.length) return
        root._syncingModel = true
        if (remote)
            root.remoteModel = values[index]
        else
            root.localModel = values[index]
        root._syncingModel = false
    }

    function ensureConfiguredModel(remote) {
        if (root._syncingModel) return
        var value = remote ? root.remoteModel : root.localModel
        var values = (remote ? root.remoteModels : root.localModels).slice()
        if (value.length > 0 && values.indexOf(value) < 0) {
            values.unshift(value)
            if (remote)
                root.remoteModels = values
            else
                root.localModels = values
        }
        var combo = remote ? remoteModelCombo : localModelCombo
        combo.currentIndex = values.indexOf(value)
    }

    function resetModelOptions(remote) {
        var value = remote ? root.remoteModel : root.localModel
        var values = value.length > 0 ? [value] : []
        if (remote) {
            root.remoteModels = values
            remoteModelCombo.currentIndex = values.length > 0 ? 0 : -1
        } else {
            root.localModels = values
            localModelCombo.currentIndex = values.length > 0 ? 0 : -1
        }
    }

    function setAvailableModels(provider, models) {
        var remote = provider !== "ollama"
        var values = []
        for (var i = 0; i < models.length; i++) {
            var value = String(models[i]).trim()
            if (value.length > 0 && values.indexOf(value) < 0)
                values.push(value)
        }
        var selected = remote ? root.remoteModel : root.localModel
        if (values.indexOf(selected) < 0)
            selected = values.length > 0 ? values[0] : ""
        root._syncingModel = true
        if (remote) {
            root.remoteModels = values
            root.remoteModel = selected
            remoteModelCombo.currentIndex = values.indexOf(selected)
        } else {
            root.localModels = values
            root.localModel = selected
            localModelCombo.currentIndex = values.indexOf(selected)
        }
        root._syncingModel = false
    }
}
