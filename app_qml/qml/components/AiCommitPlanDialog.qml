import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.DialogBoxCore {
    id: dlg

    property string _preparedRequestId: ""
    property string _previewTitle: ""
    property string _previewText: ""
    property var _groups: AiCommitPlanBridge ? AiCommitPlanBridge.planModel.groups : []
    property var _targetIds: {
        var values = [""]
        for (var i = 0; i < dlg._groups.length; i++)
            values.push(dlg._groups[i].groupId)
        return values
    }
    property var _targetLabels: {
        var values = ["未分配"]
        for (var i = 0; i < dlg._groups.length; i++)
            values.push((i + 1) + ". " + (dlg._groups[i].title || dlg._groups[i].groupId))
        return values
    }

    footer: Component {
        RowLayout {
            spacing: Fluent.Enums.spacing.s
            Fluent.ButtonCore {
                text: AiCommitPlanBridge && AiCommitPlanBridge.busy ? "取消生成" : "重新生成"
                width: Fluent.Enums.dialog.buttonWidth
                height: Fluent.Enums.dialog.buttonHeight
                onClicked: {
                    if (AiCommitPlanBridge.busy) {
                        AiCommitPlanBridge.cancelCurrent()
                        dlg._preparedRequestId = ""
                    } else {
                        AiCommitPlanBridge.preparePlan()
                    }
                }
            }
            Fluent.ButtonCore {
                text: "关闭"
                style: Fluent.Enums.button.style_primary
                width: Fluent.Enums.dialog.buttonWidth
                height: Fluent.Enums.dialog.buttonHeight
                onClicked: dlg.reject()
            }
        }
    }

    function openPlanner() {
        dlg.open()
        if (AiCommitPlanBridge && !AiCommitPlanBridge.planModel.hasPlan
                && !AiCommitPlanBridge.busy)
            AiCommitPlanBridge.preparePlan()
    }

    Connections {
        target: AiCommitPlanBridge
        function onContextPrepared(requestId, isRemote, fileCount, characterCount, summary) {
            dlg._preparedRequestId = requestId
            if (isRemote) {
                remotePlanConfirm.content = summary + "\n将发送 " + fileCount
                    + " 个变更，约 " + characterCount + " 个字符。\n"
                    + "确认后才会向远程模型发送源码差异。"
                remotePlanConfirm.open()
            } else {
                AiCommitPlanBridge.generatePrepared(requestId, false)
            }
        }
        function onPlanReady(ok, message) {
            dlg._preparedRequestId = ""
            if (ok)
                Fluent.NotificationManager.toast.success(dlg, "提交计划已生成", message)
        }
        function onErrorOccurred(message) {
            dlg._preparedRequestId = ""
            Fluent.NotificationManager.toast.error(dlg, "提交规划失败", message)
        }
    }

    ColumnLayout {
        width: 920
        spacing: Fluent.Enums.spacing.m

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "AI 文件级提交计划"
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.subtitle
                font.bold: true
            }
            Item { Layout.fillWidth: true }
            Text {
                text: {
                    if (!AiCommitPlanBridge || !AiCommitPlanBridge.planModel.hasPlan)
                        return AiCommitPlanBridge && AiCommitPlanBridge.busy ? "正在生成…" : "尚未生成"
                    if (AiCommitPlanBridge.planModel.stale) return "计划已过期"
                    if (AiCommitPlanBridge.planModel.executable) return "覆盖校验通过"
                    return AiCommitPlanBridge.planModel.valid ? "仅可查看" : "需要调整"
                }
                color: AiCommitPlanBridge && AiCommitPlanBridge.planModel.executable
                    ? Fluent.Enums.statusLevel.successColor : Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
            }
        }

        Text {
            Layout.fillWidth: true
            text: AiCommitPlanBridge ? AiCommitPlanBridge.planModel.summary : ""
            visible: text.length > 0
            color: Fluent.Enums.textColor.secondary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.body
            wrapMode: Text.WordWrap
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 520
            radius: Fluent.Enums.radius.medium
            color: Fluent.Enums.cardColor
            border.width: Fluent.Enums.border.normal
            border.color: Fluent.Enums.stateColor.border

            RowLayout {
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.m
                spacing: Fluent.Enums.spacing.m

                ColumnLayout {
                    Layout.preferredWidth: 230
                    Layout.fillHeight: true
                    spacing: Fluent.Enums.spacing.s
                    Text {
                        text: "未分配改动"
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.body
                        font.bold: true
                    }
                    Fluent.ScrollArea {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        padding: 0
                        Column {
                            width: parent ? parent.width : 0
                            spacing: Fluent.Enums.spacing.s
                            Repeater {
                                model: AiCommitPlanBridge ? AiCommitPlanBridge.planModel.unassignedChanges : []
                                delegate: changeRowDelegate
                            }
                            Text {
                                visible: AiCommitPlanBridge
                                    && AiCommitPlanBridge.planModel.unassignedChanges.length === 0
                                text: "全部改动已分配"
                                color: Fluent.Enums.textColor.tertiary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.caption
                            }
                        }
                    }
                    Fluent.Button {
                        Layout.fillWidth: true
                        text: "新增提交组"
                        enabled: AiCommitPlanBridge && AiCommitPlanBridge.planModel.hasPlan
                        onClicked: AiCommitPlanBridge.planModel.addGroup()
                    }
                }

                Rectangle {
                    Layout.fillHeight: true
                    width: 1
                    color: Fluent.Enums.dividerColor
                }

                Fluent.ScrollArea {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    padding: 0
                    Column {
                        width: parent ? parent.width : 0
                        spacing: Fluent.Enums.spacing.m

                        Repeater {
                            model: dlg._groups
                            delegate: Rectangle {
                                id: groupCard
                                required property var modelData
                                required property int index
                                property var group: modelData
                                width: parent ? parent.width : 0
                                height: groupLayout.implicitHeight + Fluent.Enums.spacing.m * 2
                                radius: Fluent.Enums.radius.medium
                                color: Fluent.Enums.stateColor.settingCardBg
                                border.width: Fluent.Enums.border.normal
                                border.color: Fluent.Enums.stateColor.settingCardBorder

                                ColumnLayout {
                                    id: groupLayout
                                    anchors.fill: parent
                                    anchors.margins: Fluent.Enums.spacing.m
                                    spacing: Fluent.Enums.spacing.s

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text {
                                            text: "提交 " + (groupCard.index + 1)
                                            color: Fluent.Enums.textColor.primary
                                            font.family: Fluent.Enums.fontFamily
                                            font.pixelSize: Fluent.Enums.typography.body
                                            font.bold: true
                                        }
                                        Text {
                                            text: groupCard.group.dependsOn.length > 0
                                                ? "依赖：" + groupCard.group.dependsOn.join(", ") : ""
                                            visible: text.length > 0
                                            color: Fluent.Enums.textColor.tertiary
                                            font.family: Fluent.Enums.fontFamily
                                            font.pixelSize: Fluent.Enums.typography.caption
                                        }
                                        Item { Layout.fillWidth: true }
                                        Fluent.Button {
                                            text: "↑"
                                            enabled: groupCard.index > 0
                                            onClicked: AiCommitPlanBridge.planModel.moveGroup(
                                                groupCard.group.groupId, groupCard.index - 1
                                            )
                                        }
                                        Fluent.Button {
                                            text: "↓"
                                            enabled: groupCard.index + 1 < dlg._groups.length
                                            onClicked: AiCommitPlanBridge.planModel.moveGroup(
                                                groupCard.group.groupId, groupCard.index + 1
                                            )
                                        }
                                        Fluent.Button {
                                            text: "删除空组"
                                            enabled: groupCard.group.changes.length === 0
                                            style: Fluent.Enums.button.style_transparent
                                            onClicked: AiCommitPlanBridge.planModel.removeEmptyGroup(
                                                groupCard.group.groupId
                                            )
                                        }
                                    }

                                    Fluent.LineEdit {
                                        id: titleInput
                                        Layout.fillWidth: true
                                        text: groupCard.group.title
                                        placeholderText: "提交标题"
                                    }
                                    Fluent.TextEdit {
                                        id: bodyInput
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 58
                                        text: groupCard.group.body
                                        placeholderText: "提交正文（可选）"
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text {
                                            Layout.fillWidth: true
                                            text: groupCard.group.rationale
                                            color: Fluent.Enums.textColor.tertiary
                                            font.family: Fluent.Enums.fontFamily
                                            font.pixelSize: Fluent.Enums.typography.caption
                                            wrapMode: Text.WordWrap
                                        }
                                        Fluent.Button {
                                            text: "保存信息"
                                            onClicked: AiCommitPlanBridge.planModel.updateGroupMessage(
                                                groupCard.group.groupId,
                                                titleInput.text,
                                                bodyInput.text
                                            )
                                        }
                                        Fluent.Button {
                                            text: "查看差异"
                                            enabled: groupCard.group.changes.length > 0
                                            onClicked: {
                                                dlg._previewTitle = titleInput.text || groupCard.group.groupId
                                                dlg._previewText = AiCommitPlanBridge.planModel.getGroupPatch(
                                                    groupCard.group.groupId
                                                )
                                                patchPreview.open()
                                            }
                                        }
                                    }

                                    Repeater {
                                        model: groupCard.group.changes
                                        delegate: changeRowDelegate
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Repeater {
            model: AiCommitPlanBridge ? AiCommitPlanBridge.planModel.issues : []
            delegate: Text {
                required property var modelData
                Layout.fillWidth: true
                text: (modelData.severity === "error" ? "错误：" : "提示：") + modelData.message
                color: modelData.severity === "error"
                    ? Fluent.Enums.statusLevel.errorColor : Fluent.Enums.textColor.tertiary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                wrapMode: Text.WordWrap
            }
        }
    }

    Component {
        id: changeRowDelegate
        Rectangle {
            required property var modelData
            property var change: modelData
            width: parent ? parent.width : 0
            height: changeLayout.implicitHeight + Fluent.Enums.spacing.s * 2
            radius: Fluent.Enums.radius.small
            color: Fluent.Enums.stateColor.hover

            ColumnLayout {
                id: changeLayout
                anchors.fill: parent
                anchors.margins: Fluent.Enums.spacing.s
                spacing: Fluent.Enums.spacing.xs
                Text {
                    Layout.fillWidth: true
                    text: change.path
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    elide: Text.ElideMiddle
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: change.status + "  +" + change.additions + " / -" + change.deletions
                        color: Fluent.Enums.textColor.tertiary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.caption
                    }
                    Item { Layout.fillWidth: true }
                    Fluent.ComboBox {
                        Layout.preferredWidth: 160
                        model: dlg._targetLabels
                        currentIndex: Math.max(0, dlg._targetIds.indexOf(change.groupId))
                        onActivated: function(targetIndex) {
                            AiCommitPlanBridge.planModel.moveChange(
                                change.changeId, dlg._targetIds[targetIndex]
                            )
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: change.unsupportedReason.length > 0
                    text: change.unsupportedReason
                    color: Fluent.Enums.statusLevel.warningColor
                    font.family: Fluent.Enums.fontFamily
                    font.pixelSize: Fluent.Enums.typography.caption
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    Fluent.MessageBox {
        id: remotePlanConfirm
        title: "确认发送工作区差异到远程模型"
        confirmText: "确认发送"
        cancelText: "取消"
        onAccepted: AiCommitPlanBridge.generatePrepared(dlg._preparedRequestId, true)
        onRejected: {
            AiCommitPlanBridge.cancelPrepared(dlg._preparedRequestId)
            dlg._preparedRequestId = ""
        }
    }

    Fluent.MessageBox {
        id: patchPreview
        title: "计划差异：" + dlg._previewTitle
        confirmText: "关闭"
        cancelText: ""
        ColumnLayout {
            width: 760
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 480
                color: Fluent.Enums.cardColor
                Fluent.ScrollArea {
                    anchors.fill: parent
                    padding: Fluent.Enums.spacing.s
                    orientation: Qt.Horizontal | Qt.Vertical
                    TextEdit {
                        width: Math.max(parent ? parent.width : 0, paintedWidth)
                        height: Math.max(1, paintedHeight)
                        readOnly: true
                        selectByMouse: true
                        textFormat: TextEdit.PlainText
                        wrapMode: TextEdit.NoWrap
                        text: dlg._previewText
                        color: Fluent.Enums.textColor.primary
                        font.family: "Consolas, Cascadia Code, monospace"
                        font.pixelSize: Fluent.Enums.typography.caption
                    }
                }
            }
        }
    }
}
