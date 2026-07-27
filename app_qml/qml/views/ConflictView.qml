// 冲突视图(阶段 3:迁移 conflict_interface.py)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent
import "../components"

Item {
    id: root

    property bool merging: false
    property string operation: ""
    property string _conflictsRequestRepoPath: ""
    property bool resolveBusy: false
    property int resolveCooldown: 0
    ListModel { id: conflictModel }

    Timer {
        id: resolveCooldownTimer
        interval: 1000
        repeat: true
        onTriggered: {
            root.resolveCooldown--
            if (root.resolveCooldown <= 0) {
                root.resolveCooldown = 0
                stop()
            }
        }
    }

    function clearModel() {
        root.merging = false
        root.operation = ""
        root._conflictsRequestRepoPath = ""
        conflictModel.clear()
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) { clearModel(); return }
        root._conflictsRequestRepoPath = GitBridge.repoPath
        GitBridge.requestConflicts()  // 异步,结果经 conflictsReady 回传
    }

    function _operationText() {
        if (root.operation === "merge") return "合并"
        if (root.operation === "rebase") return "Rebase"
        if (root.operation === "cherry-pick") return "Cherry-pick"
        if (root.operation === "revert") return "Revert"
        return ""
    }

    function _startResolveCooldown() {
        root.resolveCooldown = 3
        resolveCooldownTimer.restart()
    }

    function _op(task, isResolve) {
        if (!task) return
        if (isResolve) {
            root.resolveBusy = true
            root._startResolveCooldown()
            task.finished.connect(function() { root.resolveBusy = false })
        }
        task.succeeded.connect(function(result) {
            if (result && result[0]) root.reload()
        })
    }

    function _resolve(task) {
        if (root.resolveBusy || root.resolveCooldown > 0) return
        root._op(task, true)
    }

    function _resolveText(label) {
        if (root.resolveBusy) return "处理中…"
        if (root.resolveCooldown > 0) return label + " (" + root.resolveCooldown + "s)"
        return label
    }

    function _continueOperation() {
        if (root.operation === "merge") root._op(GitBridge.continueMerge())
        else if (root.operation === "rebase") root._op(GitBridge.continueRebase())
        else if (root.operation === "cherry-pick") root._op(GitBridge.continueCherryPick())
        else if (root.operation === "revert") root._op(GitBridge.continueRevert())
    }

    function _abortOperation() {
        if (root.operation === "merge") root._op(GitBridge.abortMerge())
        else if (root.operation === "rebase") root._op(GitBridge.abortRebase())
        else if (root.operation === "cherry-pick") root._op(GitBridge.abortCherryPick())
        else if (root.operation === "revert") root._op(GitBridge.abortRevert())
    }

    function _skipOperation() {
        if (root.operation === "rebase") root._op(GitBridge.skipRebase())
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onRepoPathChanged(path) {
            root.clearModel()
            root.reload()
        }
        function onConflictStateReady(repoPath, operation) {
            if (!GitBridge || repoPath !== GitBridge.repoPath
                    || repoPath !== root._conflictsRequestRepoPath) return
            root.operation = operation || ""
            root.merging = root.operation.length > 0
        }
        function onConflictsReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== root._conflictsRequestRepoPath) return
            conflictModel.clear()
            for (var i = 0; i < list.length; i++) conflictModel.append(list[i])
        }
    }
    Component.onCompleted: root.reload()

    Fluent.ScrollArea {
        anchors.fill: parent
        Column {
            width: parent ? parent.width : 0
            spacing: Fluent.Enums.spacing.l
            topPadding: Fluent.Enums.spacing.xl
            bottomPadding: Fluent.Enums.spacing.xl
            property real sidePad: Math.max(Fluent.Enums.spacing.xxl, (width - 980) / 2)
            leftPadding: sidePad
            rightPadding: sidePad
            readonly property real cw: width - sidePad * 2

            // 标题栏
            RowLayout {
                width: parent.cw
                Text {
                    text: "冲突解决"
                    font.pixelSize: Fluent.Enums.typography.displayLarge
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                }
                Item { Layout.fillWidth: true }
                Fluent.Button {
                    text: "刷新"
                    icon: Fluent.Enums.icon.arrow_sync
                    enabled: !root.resolveBusy
                    onClicked: root.reload()
                }
                Fluent.Button {
                    text: root.operation === "merge" ? "完成合并" : "继续"
                    visible: root.operation === "merge" || root.operation === "rebase" || root.operation === "cherry-pick" || root.operation === "revert"
                    onClicked: root._continueOperation()
                }
                Fluent.Button {
                    text: "跳过"
                    visible: root.operation === "rebase"
                    style: Fluent.Enums.button.style_transparent
                    onClicked: root._skipOperation()
                }
                Fluent.Button {
                    text: "中止"
                    visible: root.merging
                    style: Fluent.Enums.button.style_transparent
                    onClicked: root._abortOperation()
                }
            }

            // 状态卡片
            Fluent.Card {
                width: parent.cw
                height: statusRow.implicitHeight + Fluent.Enums.spacing.l * 2
                RowLayout {
                    id: statusRow
                    anchors.fill: parent
                    spacing: Fluent.Enums.spacing.m
                    Fluent.Icon {
                        icon: root.merging ? Fluent.Enums.icon.warning : Fluent.Enums.icon.checkmark_circle
                        iconSize: Fluent.Enums.iconSize.l
                        color: root.merging ? Fluent.Enums.statusLevel.warningColor : Fluent.Enums.statusLevel.successColor
                    }
                    Text {
                        Layout.fillWidth: true
                        text: !root.merging ? "当前没有 Git 中途操作或冲突"
                              : (conflictModel.count > 0 ? (root._operationText() + " 中发现 " + conflictModel.count + " 个冲突文件") : (root._operationText() + " 中，冲突已解决，请点击继续完成"))
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.body
                    }
                }
            }

            // 冲突文件列表
            Column {
                width: parent.cw
                spacing: Fluent.Enums.spacing.m
                visible: conflictModel.count > 0

                RowLayout {
                    width: parent.width
                    Text {
                        text: "冲突文件"
                        color: Fluent.Enums.textColor.primary
                        font.family: Fluent.Enums.fontFamily
                        font.pixelSize: Fluent.Enums.typography.subtitle
                        font.bold: true
                    }
                    Item { Layout.fillWidth: true }
                    Fluent.Button {
                        text: root._resolveText("全部本地优先")
                        style: Fluent.Enums.button.style_filled
                        level: Fluent.Enums.statusLevel.success
                        enabled: conflictModel.count > 0 && !root.resolveBusy
                                 && root.resolveCooldown === 0
                        onClicked: root._resolve(GitBridge.resolveAllWithOurs())
                    }
                    Fluent.Button {
                        text: root._resolveText("全部远程优先")
                        style: Fluent.Enums.button.style_filled
                        level: Fluent.Enums.statusLevel.warning
                        enabled: conflictModel.count > 0 && !root.resolveBusy
                                 && root.resolveCooldown === 0
                        onClicked: root._resolve(GitBridge.resolveAllWithTheirs())
                    }
                }

                Repeater {
                    model: conflictModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: confRow.implicitHeight + Fluent.Enums.spacing.l * 2
                        RowLayout {
                            id: confRow
                            anchors.fill: parent
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.document_error
                                iconSize: Fluent.Enums.iconSize.l
                                color: Fluent.Enums.statusLevel.warningColor
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
                                    text: model.hasConflictMarkers ? "含冲突标记 <<<<<<< >>>>>>>" : "二进制或删除冲突"
                                    color: Fluent.Enums.textColor.tertiary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.caption
                                }
                            }
                            Fluent.Button {
                                text: "查看冲突"
                                style: Fluent.Enums.button.style_transparent
                                visible: model.hasConflictMarkers
                                onClicked: conflictViewer.openFor(model.path)
                            }
                            Fluent.Button {
                                text: root._resolveText("本地优先")
                                style: Fluent.Enums.button.style_filled
                                level: Fluent.Enums.statusLevel.success
                                enabled: !root.resolveBusy && root.resolveCooldown === 0
                                onClicked: root._resolve(GitBridge.resolveWithOurs(model.path))
                            }
                            Fluent.Button {
                                text: root._resolveText("远程优先")
                                style: Fluent.Enums.button.style_filled
                                level: Fluent.Enums.statusLevel.warning
                                enabled: !root.resolveBusy && root.resolveCooldown === 0
                                onClicked: root._resolve(GitBridge.resolveWithTheirs(model.path))
                            }
                        }
                    }
                }
            }
        }
    }

    // 冲突内容查看
    ConflictViewerDialog { id: conflictViewer }
}
