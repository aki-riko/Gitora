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
    property string _advancedRequestRepoPath: ""
    property bool _advancedRequesting: false
    property bool _reloadPending: false
    ListModel { id: worktreeModel }
    ListModel { id: submoduleModel }

    function clearModels() {
        worktreeModel.clear()
        submoduleModel.clear()
        root._lfsOutput = ""
        root._bisectOutput = ""
        root._advancedRequestRepoPath = ""
        root._advancedRequesting = false
        root._reloadPending = false
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) {
            clearModels()
            return
        }
        if (!root.visible) {
            root._reloadPending = true
            return
        }
        if (root._advancedRequesting) {
            root._reloadPending = true
            return
        }
        root._advancedRequestRepoPath = GitBridge.repoPath
        root._advancedRequesting = true
        root._reloadPending = false
        GitBridge.requestAdvancedState()
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
        function onStatusChanged() {
            root._reloadPending = true
            if (root.visible) root.reload()
        }
        function onRepoPathChanged(path) {
            root.clearModels()
            root._reloadPending = true
            if (root.visible) Qt.callLater(function() { root.reload() })
        }
        function onAdvancedStateReady(repoPath, worktrees, submodules) {
            if (!GitBridge || repoPath !== GitBridge.repoPath
                    || repoPath !== root._advancedRequestRepoPath) return
            worktreeModel.clear()
            for (var i = 0; i < worktrees.length; i++) worktreeModel.append(worktrees[i])
            submoduleModel.clear()
            for (var j = 0; j < submodules.length; j++) submoduleModel.append(submodules[j])
            root._advancedRequesting = false
            root._advancedRequestRepoPath = ""
            if (root._reloadPending && root.visible)
                Qt.callLater(function() { root.reload() })
        }
    }

    // worktree/submodule 的外部变化不一定改变 status/refs，需在本页可见时单独探查。
    Timer {
        interval: GitBridge.pollIntervalMs
        running: root.visible && !!GitBridge && !!GitBridge.repoPath
        repeat: true
        onTriggered: {
            if (!root._advancedRequesting) root.reload()
        }
    }

    onVisibleChanged: {
        if (visible) {
            root._reloadPending = true
            Qt.callLater(function() { root.reload() })
        }
    }
    Component.onCompleted: {
        root._reloadPending = true
        if (root.visible) Qt.callLater(function() { root.reload() })
    }

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

            Text {
                visible: root._advancedRequesting
                text: "正在后台读取高级仓库信息…"
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.body
            }

            Fluent.SettingsCardGroup {
                title: "多工作树"
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
                                placeholderText: "工作树路径"
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
                                text: "清理失效项"
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
                                    text: (model.branch || (model.detached ? "游离状态" : "")) + "  " + model.shortHead
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
                title: "子模块"
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
                            text: submoduleModel.count > 0 ? ("已配置 " + submoduleModel.count + " 个子模块") : "当前仓库没有子模块"
                            color: Fluent.Enums.textColor.primary
                            font.family: Fluent.Enums.fontFamily
                            font.pixelSize: Fluent.Enums.typography.body
                        }
                        Fluent.Button {
                            text: "更新"
                            onClicked: root._op(GitBridge.submoduleUpdate(true, true))
                        }
                        Fluent.Button {
                            text: "同步"
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
                title: "Git 大文件存储（LFS）"
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
                                placeholderText: "远程仓库"
                            }
                            Fluent.LineEdit {
                                id: lfsBranchInput
                                Layout.preferredWidth: 160
                                text: "HEAD"
                                placeholderText: "分支或引用"
                            }
                            Item { Layout.fillWidth: true }
                            Fluent.Button {
                                text: "查看状态"
                                onClicked: root._setOutput(GitBridge.lfsStatus(), "lfs")
                            }
                            Fluent.Button {
                                text: "拉取"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: GitBridge.lfsPull()
                            }
                            Fluent.Button {
                                text: "推送"
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
                title: "二分定位"
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
                                placeholderText: "已知正常的版本"
                            }
                            Fluent.LineEdit {
                                id: bisectBadInput
                                Layout.fillWidth: true
                                text: "HEAD"
                                placeholderText: "已知异常的版本"
                            }
                            Fluent.Button {
                                text: "开始定位"
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
                                placeholderText: "版本（留空为当前版本）"
                            }
                            Fluent.Button { text: "标记正常"; onClicked: root._setOutput(GitBridge.bisectGood(bisectMarkInput.text), "bisect") }
                            Fluent.Button { text: "标记异常"; onClicked: root._setOutput(GitBridge.bisectBad(bisectMarkInput.text), "bisect") }
                            Fluent.Button { text: "跳过"; style: Fluent.Enums.button.style_transparent; onClicked: root._setOutput(GitBridge.bisectSkip(bisectMarkInput.text), "bisect") }
                            Fluent.Button { text: "查看记录"; style: Fluent.Enums.button.style_transparent; onClicked: root._setOutput(GitBridge.bisectLog(), "bisect") }
                            Fluent.Button { text: "结束定位"; style: Fluent.Enums.button.style_transparent; onClicked: root._setOutput(GitBridge.bisectReset(), "bisect") }
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
        title: "确认移除工作树"
        countdown: 3
        content: "将移除工作树：\n" + root._pendingWorktreeRemove + "\n请确认该工作树中没有需要保留的未提交修改。"
        onConfirmed: {
            if (root._pendingWorktreeRemove)
                root._op(GitBridge.removeWorktree(root._pendingWorktreeRemove, false))
            root._pendingWorktreeRemove = ""
        }
    }
}
