import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

ColumnLayout {
    id: root
    objectName: "commitComposer"

    property alias titleText: commitTitleInput.text
    property alias bodyText: commitBodyInput.text
    property bool bodyExpanded: false
    property bool aiBusy: false
    property bool aiActionEnabled: false
    property bool planActionEnabled: false
    property bool commitActionEnabled: false
    property bool quickPushActionEnabled: false
    readonly property bool hasTitle: commitTitleInput.text.trim().length > 0
    readonly property bool compact: width < 900

    signal aiRequested()
    signal planRequested()
    signal commitRequested()
    signal amendRequested()
    signal quickPushRequested()

    spacing: Fluent.Enums.spacing.s

    GridLayout {
        Layout.fillWidth: true
        columns: root.compact ? 1 : 2
        columnSpacing: Fluent.Enums.spacing.m
        rowSpacing: Fluent.Enums.spacing.s

        RowLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Fluent.Enums.spacing.s

            Fluent.LineEdit {
                id: commitTitleInput
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                placeholderText: "提交标题"
            }

            Fluent.Button {
                text: root.bodyExpanded ? "收起正文"
                    : commitBodyInput.text.trim().length > 0 ? "编辑正文" : "添加正文"
                onClicked: {
                    root.bodyExpanded = !root.bodyExpanded
                    if (root.bodyExpanded)
                        Qt.callLater(function() { commitBodyInput.setFocus() })
                }
            }
        }

        RowLayout {
            Layout.fillWidth: root.compact
            Layout.alignment: Qt.AlignRight
            spacing: Fluent.Enums.spacing.s

            Item { Layout.fillWidth: true }

            Fluent.Button {
                objectName: "aiGenerateButton"
                text: root.aiBusy ? "生成中…" : "AI 生成"
                feature: root.aiBusy
                    ? Fluent.Enums.button.feature_indeterminate_ring
                    : Fluent.Enums.button.feature_none
                toolTipText: root.aiBusy ? "取消生成" : ""
                enabled: root.aiActionEnabled
                onClicked: root.aiRequested()
            }

            Fluent.Button {
                text: "规划提交"
                enabled: root.planActionEnabled
                onClicked: root.planRequested()
            }

            Fluent.Button {
                text: "提交"
                style: Fluent.Enums.button.style_primary
                enabled: root.commitActionEnabled
                feature: Fluent.Enums.button.feature_split
                menuItems: [
                    { "text": "修补上次提交", "icon": Fluent.Enums.icon.edit }
                ]
                onClicked: root.commitRequested()
                onMenuItemClicked: function(index, text) {
                    if (index === 0) root.amendRequested()
                }
            }

            Fluent.Button {
                text: "一键提交推送"
                enabled: root.quickPushActionEnabled
                onClicked: root.quickPushRequested()
            }
        }
    }

    Fluent.TextEdit {
        id: commitBodyInput
        Layout.fillWidth: true
        Layout.preferredHeight: 76
        visible: root.bodyExpanded
        placeholderText: "提交正文（可选）"
        showScrollIndicator: true
    }

    function message() {
        var title = commitTitleInput.text.trim()
        var body = commitBodyInput.text.trim()
        return title + (body.length > 0 ? "\n\n" + body : "")
    }

    function setMessage(title, body) {
        commitTitleInput.text = title || ""
        commitBodyInput.text = body || ""
        root.bodyExpanded = commitBodyInput.text.trim().length > 0
    }

    function clear() {
        commitTitleInput.text = ""
        commitBodyInput.text = ""
        root.bodyExpanded = false
    }
}
