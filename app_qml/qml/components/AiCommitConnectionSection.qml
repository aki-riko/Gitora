import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

ColumnLayout {
    id: root

    property bool compact: false
    property bool hasStoredApiKey: false
    property string credentialStatusText: ""
    property color credentialStatusColor: Fluent.Enums.textColor.tertiary
    property alias providerIndex: providerCombo.currentIndex
    property alias localEndpoint: localEndpointInput.text
    property alias localModel: localModelInput.text
    property alias remoteEndpoint: remoteEndpointInput.text
    property alias remoteModel: remoteModelInput.text
    property alias apiKeyEnvironment: apiKeyEnvInput.text
    property alias credentialInput: apiKeyInput.text
    readonly property bool isRemote: providerCombo.currentIndex === 1

    signal deleteCredentialRequested()

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
        text: "选择模型来源，并配置连接所需的信息。"
        textFormat: Text.PlainText
        color: Fluent.Enums.textColor.tertiary
        font.family: Fluent.Enums.fontFamily
        font.pixelSize: Fluent.Enums.typography.caption
        wrapMode: Text.WordWrap
    }

    GridLayout {
        id: connectionFields
        Layout.fillWidth: true
        columns: root.compact ? 1 : 3
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
                model: ["本地 Ollama", "远程 Responses API"]
                currentIndex: 0
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: 1
            spacing: Fluent.Enums.spacing.xxs

            Text {
                text: "模型名称"
                textFormat: Text.PlainText
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }

            Fluent.LineEdit {
                id: localModelInput
                Layout.fillWidth: true
                visible: !root.isRemote
                placeholderText: "输入本地模型名称"
            }

            Fluent.LineEdit {
                id: remoteModelInput
                Layout.fillWidth: true
                visible: root.isRemote
                placeholderText: "输入远程模型名称"
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
                placeholderText: "输入 Responses API 的完整 HTTPS 地址"
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.columnSpan: connectionFields.columns === 1 ? 1 : 2
            Layout.minimumWidth: 0
            Layout.preferredWidth: connectionFields.columns === 1 ? 1 : 2
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
}
