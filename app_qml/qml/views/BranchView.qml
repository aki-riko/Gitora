// 分支视图(阶段 3:迁移 branch_interface.py)
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent
import "../components"

Item {
    id: root

    property string currentBranch: ""
    property string _mergeTarget: ""   // 待合并到当前分支的目标分支名
    property string _rebaseTarget: ""  // 当前分支要 rebase 到的目标分支名
    property string _remoteCheckoutTarget: ""
    property string _branchesRequestRepoPath: ""
    ListModel { id: localModel }
    ListModel { id: remoteModel }

    function clearModels() {
        root.currentBranch = ""
        root._branchesRequestRepoPath = ""
        localModel.clear()
        remoteModel.clear()
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) {
            clearModels()
            return
        }
        root._branchesRequestRepoPath = GitBridge.repoPath
        root.currentBranch = GitBridge.getCurrentBranch()
        GitBridge.requestBranches()  // 异步,结果经 branchesReady 回传
    }

    function _op(res) {
        if (res[0]) {
            Fluent.NotificationManager.toast.success(root, "成功", res[1] || "操作完成")
            root.reload()
        } else {
            Fluent.NotificationManager.toast.error(root, "失败", res[1] || "操作失败")
        }
    }

    function _defaultRemoteName() {
        var remotes = GitBridge ? GitBridge.getRemoteInfo() : []
        if (!remotes || remotes.length === 0) return "origin"
        for (var i = 0; i < remotes.length; i++) {
            if (remotes[i].name === "origin") return "origin"
        }
        return remotes[0].name || "origin"
    }

    function _localNameForRemote(remoteBranch) {
        var idx = remoteBranch.indexOf("/")
        return idx >= 0 ? remoteBranch.substring(idx + 1) : remoteBranch
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onRepoPathChanged(path) {
            root.clearModels()
            root.reload()
        }
        function onBranchesReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== root._branchesRequestRepoPath) return
            localModel.clear(); remoteModel.clear()
            for (var i = 0; i < list.length; i++) {
                if (list[i].isRemote) remoteModel.append(list[i])
                else localModel.append(list[i])
            }
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
                    text: "分支"
                    font.pixelSize: Fluent.Enums.typography.displayLarge
                    font.bold: true
                    color: Fluent.Enums.textColor.primary
                    font.family: Fluent.Enums.fontFamily
                }
                Item { Layout.fillWidth: true }
                Fluent.Button { text: "刷新全部远程"; icon: Fluent.Enums.icon.arrow_sync; onClicked: GitBridge.fetchAll() }
                Fluent.Button {
                    text: "远程"
                    icon: Fluent.Enums.icon.globe
                    onClicked: remoteManageDialog.openPanel()
                }
                Fluent.Button {
                    text: "新建分支"
                    style: Fluent.Enums.button.style_primary
                    icon: Fluent.Enums.icon.add
                    onClicked: createDialog.open()
                }
            }

            // 本地分支
            Fluent.SettingsCardGroup {
                title: "本地分支"
                width: parent.cw
                Repeater {
                    model: localModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: lbRow.implicitHeight + Fluent.Enums.spacing.l * 2
                        RowLayout {
                            id: lbRow
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.l
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.branch_fork
                                iconSize: Fluent.Enums.iconSize.l
                                color: model.isCurrent ? Fluent.Enums.accentColor : Fluent.Enums.textColor.tertiary
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    text: model.name + (model.isCurrent ? "  (当前)" : "")
                                    color: Fluent.Enums.textColor.primary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.body
                                    font.bold: model.isCurrent
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: {
                                        var parts = []
                                        if (model.tracking) parts.push("跟踪 " + model.tracking)
                                        if (model.ahead > 0) parts.push("↑" + model.ahead)
                                        if (model.behind > 0) parts.push("↓" + model.behind)
                                        return parts.length > 0 ? parts.join("  ") : "本地分支"
                                    }
                                    color: Fluent.Enums.textColor.tertiary
                                    font.family: Fluent.Enums.fontFamily
                                    font.pixelSize: Fluent.Enums.typography.caption
                                    elide: Text.ElideRight
                                }
                            }
                            Fluent.Button {
                                text: model.isCurrent ? "当前" : "切换"
                                enabled: !model.isCurrent
                                onClicked: root._op(GitBridge.checkoutBranch(model.name))
                            }
                            Fluent.Button {
                                text: "合并"
                                visible: !model.isCurrent
                                // 把该分支合并到当前分支(异步,结果经全局 operationFinished 弹 toast;
                                // 冲突时 git 会中止合并并在 toast 报错,不会静默破坏工作区)
                                onClicked: {
                                    root._mergeTarget = model.name
                                    mergeConfirm.open()
                                }
                            }
                            Fluent.Button {
                                text: "Rebase"
                                style: Fluent.Enums.button.style_transparent
                                visible: !model.isCurrent
                                onClicked: {
                                    root._rebaseTarget = model.name
                                    rebaseDanger.start()
                                }
                            }
                            Fluent.Button {
                                text: "上游"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: {
                                    upstreamDialog._branch = model.name
                                    upstreamRemoteInput.text = root._defaultRemoteName()
                                    upstreamBranchInput.text = model.name
                                    upstreamDialog.open()
                                }
                            }
                            Fluent.Button {
                                text: "重命名"
                                style: Fluent.Enums.button.style_transparent
                                onClicked: {
                                    renameBranchDialog._oldBranch = model.name
                                    renameBranchInput.text = model.name
                                    renameBranchDialog.open()
                                }
                            }
                            Fluent.Button {
                                text: "删除"
                                style: Fluent.Enums.button.style_transparent
                                visible: !model.isCurrent
                                feature: Fluent.Enums.button.feature_split
                                menuItems: [
                                    { "text": "强制删除", "icon": Fluent.Enums.icon.warning }
                                ]
                                onClicked: root._op(GitBridge.deleteBranch(model.name, false))
                                onMenuItemClicked: function(index, text) {
                                    if (index !== 0) return
                                    forceDeleteBranchDanger._branch = model.name
                                    forceDeleteBranchDanger.start()
                                }
                            }
                        }
                    }
                }
            }

            // 远程分支
            Fluent.SettingsCardGroup {
                title: "远程分支"
                width: parent.cw
                visible: remoteModel.count > 0
                Repeater {
                    model: remoteModel
                    delegate: Fluent.Card {
                        width: parent ? parent.width : 0
                        height: rbRow.implicitHeight + Fluent.Enums.spacing.l * 2
                        RowLayout {
                            id: rbRow
                            anchors.fill: parent
                            anchors.margins: Fluent.Enums.spacing.l
                            spacing: Fluent.Enums.spacing.m
                            Fluent.Icon {
                                icon: Fluent.Enums.icon.branch_fork
                                iconSize: Fluent.Enums.iconSize.l
                                color: Fluent.Enums.textColor.tertiary
                            }
                            Text {
                                Layout.fillWidth: true
                                text: model.name
                                color: Fluent.Enums.textColor.primary
                                font.family: Fluent.Enums.fontFamily
                                font.pixelSize: Fluent.Enums.typography.body
                            }
                            Fluent.Button {
                                text: "检出"
                                onClicked: {
                                    root._remoteCheckoutTarget = model.name
                                    remoteCheckoutLocalInput.text = root._localNameForRemote(model.name)
                                    remoteCheckoutDialog.open()
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // 新建分支对话框
    Fluent.MessageBox {
        id: createDialog
        title: "新建分支"
        confirmText: "创建"
        cancelText: "取消"
        Fluent.LineEdit {
            id: newBranchInput
            width: 320
            placeholderText: "分支名称"
        }
        onAccepted: {
            if (newBranchInput.text)
                root._op(GitBridge.createBranch(newBranchInput.text, true))
            newBranchInput.text = ""
        }
    }

    // 重命名本地分支
    Fluent.MessageBox {
        id: renameBranchDialog
        title: "重命名分支"
        confirmText: "保存"
        cancelText: "取消"
        property string _oldBranch: ""
        function validate() { return renameBranchInput.text.trim().length > 0 }
        Fluent.LineEdit {
            id: renameBranchInput
            width: 320
            placeholderText: "新的分支名称"
        }
        onAccepted: {
            root._op(GitBridge.renameBranch(_oldBranch, renameBranchInput.text))
            _oldBranch = ""
            renameBranchInput.text = ""
        }
    }

    // 设置本地分支上游
    Fluent.MessageBox {
        id: upstreamDialog
        title: "设置上游分支"
        confirmText: "保存"
        cancelText: "取消"
        property string _branch: ""
        function validate() {
            return upstreamRemoteInput.text.trim().length > 0
                && upstreamBranchInput.text.trim().length > 0
        }
        ColumnLayout {
            width: 360
            spacing: Fluent.Enums.spacing.m
            Text {
                Layout.fillWidth: true
                text: "本地分支: " + upstreamDialog._branch
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
            }
            Fluent.LineEdit {
                id: upstreamRemoteInput
                Layout.fillWidth: true
                placeholderText: "远程名"
            }
            Fluent.LineEdit {
                id: upstreamBranchInput
                Layout.fillWidth: true
                placeholderText: "远程分支名(如 main)"
            }
        }
        onAccepted: {
            root._op(GitBridge.setUpstream(_branch, upstreamRemoteInput.text, upstreamBranchInput.text))
            _branch = ""
            upstreamRemoteInput.text = ""
            upstreamBranchInput.text = ""
        }
    }

    // 从远程分支创建本地跟踪分支
    Fluent.MessageBox {
        id: remoteCheckoutDialog
        title: "检出远程分支"
        confirmText: "检出"
        cancelText: "取消"
        function validate() { return remoteCheckoutLocalInput.text.trim().length > 0 }
        ColumnLayout {
            width: 360
            spacing: Fluent.Enums.spacing.m
            Text {
                Layout.fillWidth: true
                text: "远程分支: " + root._remoteCheckoutTarget
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideRight
            }
            Fluent.LineEdit {
                id: remoteCheckoutLocalInput
                Layout.fillWidth: true
                placeholderText: "本地分支名"
            }
        }
        onAccepted: {
            root._op(GitBridge.checkoutRemoteBranch(root._remoteCheckoutTarget, remoteCheckoutLocalInput.text))
            root._remoteCheckoutTarget = ""
            remoteCheckoutLocalInput.text = ""
        }
    }

    // 合并分支确认:把 _mergeTarget 合并到当前分支
    Fluent.MessageBox {
        id: mergeConfirm
        title: "合并分支"
        content: "确定把分支 \"" + root._mergeTarget + "\" 合并到当前分支 \"" + root.currentBranch + "\" 吗?\n若产生冲突,合并会中止并提示,需手动解决。"
        confirmText: "合并"
        cancelText: "取消"
        onAccepted: {
            if (root._mergeTarget)
                GitBridge.mergeBranch(root._mergeTarget)
            root._mergeTarget = ""
        }
    }

    // 危险操作:将当前分支 rebase 到目标分支,会重写当前分支提交基底
    DangerDialog {
        id: rebaseDanger
        title: "确认 Rebase"
        countdown: 3
        content: "将当前分支 \"" + root.currentBranch + "\" rebase 到 \"" + root._rebaseTarget + "\"。\n"
            + "这会重写当前分支尚未推送的提交历史;如果产生冲突,请到冲突页继续、跳过或中止。"
        onConfirmed: {
            if (root._rebaseTarget)
                root._op(GitBridge.rebaseOnto(root._rebaseTarget))
            root._rebaseTarget = ""
        }
    }

    // 危险操作:强制删除本地分支二次确认(会丢弃该分支未合并提交)
    DangerDialog {
        id: forceDeleteBranchDanger
        title: "确认强制删除分支"
        countdown: 3
        property string _branch: ""
        content: "将强制删除本地分支 \"" + _branch + "\"。\n"
            + "即使该分支包含尚未合并的提交也会被删除。\n"
            + "此操作不可恢复,请确认这些提交不再需要。"
        onConfirmed: {
            if (_branch)
                root._op(GitBridge.deleteBranch(_branch, true))
            _branch = ""
        }
    }

    // 远程管理面板(添加/修改URL/删除)
    RemoteDialog { id: remoteManageDialog }
}
