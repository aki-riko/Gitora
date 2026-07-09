// 高级 Git 操作: worktree / submodule / LFS / bisect
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent
import "../components"

Item {
    id: root

    property string _pendingWorktreeRemove: ""
    property string _lfsOutput: ""
    property string _bisectOutput: ""
    ListModel { id: worktreeModel }
    ListModel { id: submoduleModel }

    function clearModels() {
        worktreeModel.clear()
        submoduleModel.clear()
        root._lfsOutput = ""
        root._bisectOutput = ""
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) {
            clearModels()
            return
        }
        worktreeModel.clear()
        var worktrees = GitBridge.getWorktrees()
        for (var i = 0; i < worktrees.length; i++) worktreeModel.append(worktrees[i])

        submoduleModel.clear()
        var modules = GitBridge.getSubmodules()
        for (var j = 0; j < modules.length; j++) submoduleModel.append(modules[j])
    }

    function _op(res) {
        if (res[0]) {
            Fluent.NotificationManager.toast.success(root, "成功", res[1] || "操作完成")
            root.reload()
        } else {
            Fluent.NotificationManager.toast.error(root, "失败", res[1] || "操作失败")
        }
    }

    function _setOutput(result, target) {
        if (result[0]) {
            if (target === "lfs") root._lfsOutput = result[1] || ""
            else root._bisectOutput = result[1] || ""
        } else {
            Fluent.NotificationManager.toast.error(root, "失败", result[1] || "操作失败")
        }
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onRepoPathChanged(path) {
            root.clearModels()
            root.reload()
        }
    }
    Component.onCompleted: root.reload()

    Fluent.ScrollArea {
        anchors.fill: parent

        Column {
            id: contentCol
            width: parent ? parent.width : 0
            spacing: Fluent.Enums.spacing.l
            topPadding: Fluent.Enums.spacing.xl
            bottomPadding: Fluent.Enums.spacing.xl
            property real sidePad: Math.max(Fluent.Enums.spacing.xxl, (width - 980) / 2)
            leftPadding: sidePad
            rightPadding: sidePad
            readonly property real cw: width - sidePad * 2

            Text {
                text: "高级"
                font.pixelSize: Fluent.Enums.typography.displayLarge
                font.bold: true
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
            }

            Fluent.SettingsCardGroup {
                title: "Worktree"
                width: contentCol.cw

                Fluent.Card {
                    width: parent ? parent.width : 0
                    height: worktreeForm.implicitHeight + Fluent.Enums.spacing.l * 2
                    ColumnLayout {
                        id: worktreeForm
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.l
                        spacing: Fluent.Enums.spacing.m
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.m
                            Fluent.LineEdit {
                                id: worktreePathInput
                                Layout.fillWidth: true
                                placeholderText: "Worktree 路径"
                            }
                            Fluent.LineEdit {
                                id: worktreeBranchInput
                                Layout.preferredWidth: 200
                                placeholderText: "分支名"
                            }
                            Fluent.CheckBox {
                                id: worktreeCreateBranchCheck
                                text: "新建"
                            }
                            Fluent.Button {
                                text: "添加"
                                style: Fluent.Enums.button.style_primary
                                onClicked: root._op(GitBridge.addWorktree(worktreePathInput.text, worktreeBranchInput.text, worktreeCreateBranchCheck.checked))
                            }
                            Fluent.Button {
                                text: "Prune"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: root._op(GitBridge.pruneWorktrees())
                            }
                        }
                    }
                }

                Repeater {
                    model: worktreeModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: wtRow.implicitHeight + Fluent.Enums.spacing.l * 2
                        RowLayout {
                            id: wtRow
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.l
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.branch_fork
                                iconSize: Fluent.Enums.iconSize.l
                                color: model.prunable ? Fluent.Enums.statusLevel.warningColor : Fluent.Enums.accentColor
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    Layout.fillWidth: true
                                    text: model.path
                                    color: Fluent.Enums.textColor.primary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.body
                                    elide: Text.ElideMiddle
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: (model.branch || (model.detached ? "detached" : "")) + "  " + model.shortHead
                                    color: Fluent.Enums.textColor.tertiary
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: Fluent.Enums.typography.caption
                                    elide: Text.ElideRight
                                }
                            }
                            Fluent.Button {
                                text: "移除"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: {
                                    root._pendingWorktreeRemove = model.path
                                    removeWorktreeDanger.start()
                                }
                            }
                        }
                    }
                }
            }

            Fluent.SettingsCardGroup {
                title: "Submodule"
                width: contentCol.cw

                Fluent.Card {
                    width: parent ? parent.width : 0
                    height: submoduleActions.implicitHeight + Fluent.Enums.spacing.l * 2
                    RowLayout {
                        id: submoduleActions
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.l
                        spacing: Fluent.Enums.spacing.m
                        Text {
                            Layout.fillWidth: true
                            text: submoduleModel.count > 0 ? ("已配置 " + submoduleModel.count + " 个 submodule") : "当前仓库没有 submodule"
                            color: Fluent.Enums.textColor.primary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.body
                        }
                        Fluent.Button {
                            text: "Update"
                            onClicked: root._op(GitBridge.submoduleUpdate(true, true))
                        }
                        Fluent.Button {
                            text: "Sync"
                            style: Fluent.Enums.button.style_transparent
                            onClicked: root._op(GitBridge.submoduleSync(true))
                        }
                    }
                }

                Repeater {
                    model: submoduleModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: smRow.implicitHeight + Fluent.Enums.spacing.l * 2
                        RowLayout {
                            id: smRow
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.l
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.branch
                                iconSize: Fluent.Enums.iconSize.l
                                color: model.status === "正常" ? Fluent.Enums.accentColor : Fluent.Enums.statusLevel.warningColor
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    text: model.path
                                    color: Fluent.Enums.textColor.primary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.body
                                    font.bold: true
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: model.status + "  " + model.shortHash + "  " + model.description
                                    color: Fluent.Enums.textColor.tertiary
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: Fluent.Enums.typography.caption
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }

            Fluent.SettingsCardGroup {
                title: "Git LFS"
                width: contentCol.cw

                Fluent.Card {
                    width: parent ? parent.width : 0
                    height: lfsLayout.implicitHeight + Fluent.Enums.spacing.l * 2
                    ColumnLayout {
                        id: lfsLayout
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.l
                        spacing: Fluent.Enums.spacing.m
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.m
                            Fluent.LineEdit {
                                id: lfsRemoteInput
                                Layout.preferredWidth: 160
                                text: "origin"
                                placeholderText: "remote"
                            }
                            Fluent.LineEdit {
                                id: lfsBranchInput
                                Layout.preferredWidth: 160
                                text: "HEAD"
                                placeholderText: "branch"
                            }
                            Item { Layout.fillWidth: true }
                            Fluent.Button {
                                text: "Status"
                                onClicked: root._setOutput(GitBridge.lfsStatus(), "lfs")
                            }
                            Fluent.Button {
                                text: "Pull"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: GitBridge.lfsPull()
                            }
                            Fluent.Button {
                                text: "Push"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: GitBridge.lfsPush(lfsRemoteInput.text, lfsBranchInput.text)
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 160
                            radius: Fluent.Enums.radius.medium
                            color: Fluent.Enums.cardColor
                            border.width: Fluent.Enums.border.normal
                            border.color: Fluent.Enums.stateColor.border
                            Fluent.ScrollArea {
                                anchors.fill: parent
                                anchors.margins: Fluent.Enums.spacing.s
                                padding: 0
                                TextEdit {
                                    readOnly: true
                                    selectByMouse: true
                                    textFormat: TextEdit.PlainText
                                    wrapMode: TextEdit.NoWrap
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: Fluent.Enums.typography.caption
                                    color: Fluent.Enums.textColor.primary
                                    text: root._lfsOutput
                                }
                            }
                        }
                    }
                }
            }

            Fluent.SettingsCardGroup {
                title: "Bisect"
                width: contentCol.cw

                Fluent.Card {
                    width: parent ? parent.width : 0
                    height: bisectLayout.implicitHeight + Fluent.Enums.spacing.l * 2
                    ColumnLayout {
                        id: bisectLayout
                        anchors.fill: parent
                        anchors.margins: Fluent.Enums.spacing.l
                        spacing: Fluent.Enums.spacing.m
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.m
                            Fluent.LineEdit {
                                id: bisectGoodInput
                                Layout.fillWidth: true
                                placeholderText: "good revision"
                            }
                            Fluent.LineEdit {
                                id: bisectBadInput
                                Layout.fillWidth: true
                                text: "HEAD"
                                placeholderText: "bad revision"
                            }
                            Fluent.Button {
                                text: "Start"
                                style: Fluent.Enums.button.style_primary
                                onClicked: root._setOutput(GitBridge.bisectStart(bisectGoodInput.text, bisectBadInput.text), "bisect")
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Fluent.Enums.spacing.m
                            Fluent.LineEdit {
                                id: bisectMarkInput
                                Layout.fillWidth: true
                                placeholderText: "revision(留空为当前)"
                            }
                            Fluent.Button { text: "Good"; onClicked: root._setOutput(GitBridge.bisectGood(bisectMarkInput.text), "bisect") }
                            Fluent.Button { text: "Bad"; onClicked: root._setOutput(GitBridge.bisectBad(bisectMarkInput.text), "bisect") }
                            Fluent.Button { text: "Skip"; style: Fluent.Enums.button.style_transparent; onClicked: root._setOutput(GitBridge.bisectSkip(bisectMarkInput.text), "bisect") }
                            Fluent.Button { text: "Log"; style: Fluent.Enums.button.style_transparent; onClicked: root._setOutput(GitBridge.bisectLog(), "bisect") }
                            Fluent.Button { text: "Reset"; style: Fluent.Enums.button.style_transparent; onClicked: root._setOutput(GitBridge.bisectReset(), "bisect") }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 180
                            radius: Fluent.Enums.radius.medium
                            color: Fluent.Enums.cardColor
                            border.width: Fluent.Enums.border.normal
                            border.color: Fluent.Enums.stateColor.border
                            Fluent.ScrollArea {
                                anchors.fill: parent
                                anchors.margins: Fluent.Enums.spacing.s
                                padding: 0
                                TextEdit {
                                    readOnly: true
                                    selectByMouse: true
                                    textFormat: TextEdit.PlainText
                                    wrapMode: TextEdit.NoWrap
                                    font.family: "Consolas, monospace"
                                    font.pixelSize: Fluent.Enums.typography.caption
                                    color: Fluent.Enums.textColor.primary
                                    text: root._bisectOutput
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    DangerDialog {
        id: removeWorktreeDanger
        title: "确认移除 Worktree"
        countdown: 3
        content: "将移除 worktree:\n" + root._pendingWorktreeRemove + "\n请确认该 worktree 中没有需要保留的未提交修改。"
        onConfirmed: {
            if (root._pendingWorktreeRemove)
                root._op(GitBridge.removeWorktree(root._pendingWorktreeRemove, false))
            root._pendingWorktreeRemove = ""
        }
    }
}
