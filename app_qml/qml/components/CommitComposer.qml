import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

ColumnLayout {
    id: root
    objectName: "commitComposer"

    property alias titleText: commitTitleInput.text
    property bool aiCommitActionEnabled: false
    property bool commitActionEnabled: false
    readonly property bool hasTitle: commitTitleInput.text.trim().length > 0

    signal aiCommitRequested()
    signal commitRequested()
    signal amendRequested()

    spacing: Fluent.Enums.spacing.s

    RowLayout {
        Layout.fillWidth: true
        spacing: Fluent.Enums.spacing.s

        Fluent.LineEdit {
            id: commitTitleInput
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            placeholderText: "提交标题"
        }

        Fluent.Button {
            text: "提交"
            style: Fluent.Enums.button.style_primary
            enabled: root.commitActionEnabled || root.aiCommitActionEnabled
            feature: Fluent.Enums.button.feature_split
            menuItems: [
                { "text": "AI 提交", "icon": Fluent.Enums.icon.sparkle },
                { "text": "修补上次提交", "icon": Fluent.Enums.icon.edit }
            ]
            onClicked: root.commitRequested()
            onMenuItemClicked: function(index, text) {
                if (index === 0 && root.aiCommitActionEnabled)
                    root.aiCommitRequested()
                else if (index === 1)
                    root.amendRequested()
            }
        }
    }

    function message() {
        return commitTitleInput.text.trim()
    }

    function clear() {
        commitTitleInput.text = ""
    }
}
