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
    property string _remoteDeleteTarget: ""
    property string _branchesRequestRepoPath: ""
    property var _branchMenuOwner: null
    property bool initialized: false
    readonly property bool pageActive: root.visible
        && (!root.parent || root.parent.visible)
    property var _remotes: []
    property var branchRows: []
    property int branchCount: 0
    readonly property int branchItemHeight:
        Fluent.Enums.controlSize.buttonHeight + Fluent.Enums.spacing.l * 2

    function _sectionRow(title) {
        return {
            "rowType": "section",
            "sectionTitle": title,
            "name": "",
            "isCurrent": false,
            "isRemote": false,
            "tracking": "",
            "ahead": 0,
            "behind": 0
        }
    }

    function _branchRow(branch) {
        return {
            "rowType": "branch",
            "sectionTitle": "",
            "name": branch.name || "",
            "isCurrent": !!branch.isCurrent,
            "isRemote": !!branch.isRemote,
            "tracking": branch.tracking || "",
            "ahead": branch.ahead || 0,
            "behind": branch.behind || 0
        }
    }

    function setBranches(list) {
        branchActionsMenu.close()
        root._releaseBranchMenu()
        var localRows = []
        var remoteRows = []
        for (var i = 0; i < list.length; i++) {
            var row = root._branchRow(list[i])
            if (row.isRemote) remoteRows.push(row)
            else localRows.push(row)
        }

        var rows = [root._sectionRow("本地分支")]
        rows = rows.concat(localRows)
        if (remoteRows.length > 0)
            rows = rows.concat([root._sectionRow("远程分支")], remoteRows)
        root.branchCount = list.length
        root.branchRows = rows
    }

    function clearModels() {
        branchActionsMenu.close()
        root._releaseBranchMenu()
        root.currentBranch = ""
        root._remotes = []
        root._branchesRequestRepoPath = ""
        root.branchCount = 0
        root.branchRows = []
    }

    function reload() {
        if (!GitBridge || !GitBridge.repoPath) {
            clearModels()
            return
        }
        root._branchesRequestRepoPath = GitBridge.repoPath
        GitBridge.requestCurrentBranch()
        var remoteTask = GitBridge.getRemoteInfo()
        remoteTask.succeeded.connect(function(remotes) {
            if (GitBridge && root._branchesRequestRepoPath === GitBridge.repoPath)
                root._remotes = remotes || []
        })
        GitBridge.requestBranches()  // 异步,结果经 branchesReady 回传
    }

    function _op(task) {
        if (!task) return
        task.succeeded.connect(function(result) {
            if (result && result[0]) root.reload()
        })
    }

    function _defaultRemoteName() {
        var remotes = root._remotes
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

    function _openBranchMenu(anchor, owner, branchName, isRemote, isCurrent) {
        if (!anchor || !owner) return
        if (root._branchMenuOwner && root._branchMenuOwner !== owner)
            root._branchMenuOwner.menuPinned = false
        root._branchMenuOwner = owner
        branchActionsMenu.openFor(
            anchor, branchName, isRemote, isCurrent)
    }

    function _releaseBranchMenu() {
        var owner = root._branchMenuOwner
        root._branchMenuOwner = null
        if (owner) owner.menuPinned = false
    }

    function _handleBranchAction(actionText, branchName, isRemote) {
        if (isRemote) {
            if (actionText === "删除远程分支") {
                root._remoteDeleteTarget = branchName
                deleteRemoteBranchDanger.start()
            }
        } else if (actionText === "合并到当前分支") {
            root._mergeTarget = branchName
            mergeConfirm.open()
        } else if (actionText === "Rebase 到此分支") {
            root._rebaseTarget = branchName
            rebaseDanger.start()
        } else if (actionText === "设置上游") {
            upstreamDialog._branch = branchName
            upstreamRemoteInput.text = root._defaultRemoteName()
            upstreamBranchInput.text = branchName
            upstreamDialog.open()
        } else if (actionText === "重命名") {
            renameBranchDialog._oldBranch = branchName
            renameBranchInput.text = branchName
            renameBranchDialog.open()
        } else if (actionText === "删除分支") {
            deleteBranchConfirm._branch = branchName
            deleteBranchConfirm.open()
        } else if (actionText === "强制删除") {
            forceDeleteBranchDanger._branch = branchName
            forceDeleteBranchDanger.start()
        }
    }

    Connections {
        target: GitBridge
        function onStatusChanged() { root.reload() }
        function onRepoPathChanged(path) {
            root.clearModels()
            root.reload()
        }
        function onBranchReady(repoPath, branch) {
            if (!GitBridge || repoPath !== GitBridge.repoPath
                    || repoPath !== root._branchesRequestRepoPath) return
            root.currentBranch = branch
        }
        function onBranchesReady(repoPath, list) {
            if (!GitBridge || repoPath !== GitBridge.repoPath || repoPath !== root._branchesRequestRepoPath) return
            root.setBranches(list || [])
        }
    }
    onPageActiveChanged: {
        if (!root.pageActive || !root.initialized) return
        Qt.callLater(function() {
            if (root.pageActive) root.reload()
        })
    }

    Component.onCompleted: {
        root.initialized = true
        root.reload()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        spacing: Fluent.Enums.spacing.l

        // 标题栏固定在列表之外，页面只有下面一个滚动容器。
        RowLayout {
            Layout.fillWidth: true
            Layout.maximumWidth: 980
            Layout.alignment: Qt.AlignHCenter
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
                onClicked: createBranchDialog.openFor("HEAD", true)
            }
        }

        // 本地、远程和分组标题共用一个虚拟列表，禁止嵌套滚动容器。
        Fluent.ScrollArea {
            id: branchList
            objectName: "branchList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.maximumWidth: 980
            Layout.alignment: Qt.AlignHCenter
            type: Fluent.Enums.scroll.type_list
            model: root.branchRows
            itemHeight: root.branchItemHeight
            listSpacing: Fluent.Enums.spacing.m
            listCacheBuffer: root.branchItemHeight * 2
            reuseItems: true
            bounceEnabled: false
            selectable: false
            padding: 0

            delegate: BranchRowDelegate {
                required property var modelData
                rowData: modelData
                width: ListView.view ? ListView.view.width : 0
                itemHeight: root.branchItemHeight
                onPrimaryRequested: function(branchName, isRemote, isCurrent) {
                    if (isRemote) {
                        root._remoteCheckoutTarget = branchName
                        remoteCheckoutLocalInput.text = root._localNameForRemote(branchName)
                        remoteCheckoutDialog.open()
                    } else if (!isCurrent) {
                        root._op(GitBridge.checkoutBranch(branchName))
                    }
                }
                onMenuRequested: function(
                    anchor, owner, branchName, isRemote, isCurrent
                ) {
                    root._openBranchMenu(
                        anchor, owner, branchName, isRemote, isCurrent)
                }
            }
        }
    }

    BranchActionsMenu {
        id: branchActionsMenu
        objectName: "branchActionsMenu"
        onBranchActionRequested: function(actionText, branchName, isRemote) {
            root._handleBranchAction(actionText, branchName, isRemote)
        }
        onDismissed: root._releaseBranchMenu()
    }

    // 默认从 HEAD 创建并切换；对话框内可改为任意提交并取消切换。
    CreateBranchDialog {
        id: createBranchDialog
        onOperationSucceeded: root.reload()
    }

    // 重命名本地分支
    Fluent.MessageBox {
        id: renameBranchDialog
        title: ""
        confirmText: "保存"
        cancelText: "取消"
        property string _oldBranch: ""
        function validate() { return renameBranchInput.text.trim().length > 0 }
        ColumnLayout {
            width: 320
            spacing: Fluent.Enums.spacing.m
            DialogTitle {
                objectName: "renameBranchDialogTitle"
                text: "重命名分支"
            }
            Fluent.LineEdit {
                id: renameBranchInput
                Layout.fillWidth: true
                placeholderText: "新的分支名称"
            }
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
        title: ""
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
            DialogTitle {
                objectName: "upstreamDialogTitle"
                text: "设置上游分支"
            }
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

    // 先获取远程更新，再从远程分支创建本地跟踪分支
    Fluent.MessageBox {
        id: remoteCheckoutDialog
        objectName: "remoteCheckoutDialog"
        // MessageBox 的内建标题与调用方表单是并列子项，会从同一坐标绘制。
        // 把可见标题纳入表单布局，确保标题、远程分支和输入框依次排列。
        title: ""
        confirmText: "获取并检出"
        cancelText: "取消"
        function validate() { return remoteCheckoutLocalInput.text.trim().length > 0 }
        ColumnLayout {
            width: 360
            spacing: Fluent.Enums.spacing.m
            DialogTitle {
                objectName: "remoteCheckoutDialogTitle"
                text: "获取并检出远程分支"
            }
            Text {
                objectName: "remoteCheckoutTargetLabel"
                Layout.fillWidth: true
                text: "远程分支: " + root._remoteCheckoutTarget
                color: Fluent.Enums.textColor.secondary
                font.family: Fluent.Enums.fontFamily
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideRight
            }
            Fluent.LineEdit {
                id: remoteCheckoutLocalInput
                objectName: "remoteCheckoutLocalInput"
                Layout.fillWidth: true
                placeholderText: "本地分支名"
            }
        }
        onAccepted: {
            root._op(GitBridge.fetchAndCheckoutRemoteBranch(root._remoteCheckoutTarget, remoteCheckoutLocalInput.text))
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

    // 普通删除仍需确认；Git 会拒绝删除包含未合并提交的分支。
    Fluent.MessageBox {
        id: deleteBranchConfirm
        objectName: "deleteBranchConfirm"
        title: "确认删除分支"
        content: "确定删除本地分支 \"" + _branch + "\" 吗？\n"
            + "如果分支包含尚未合并的提交，Git 会拒绝删除。"
        confirmText: "删除"
        cancelText: "取消"
        property string _branch: ""
        onAccepted: {
            if (_branch)
                root._op(GitBridge.deleteBranch(_branch, false))
            _branch = ""
        }
        onRejected: _branch = ""
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
        objectName: "forceDeleteBranchDanger"
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

    // 危险操作:删除远程仓库中的分支，但保留本地分支
    DangerDialog {
        id: deleteRemoteBranchDanger
        title: "确认删除远程分支"
        countdown: 3
        content: "将删除远程分支 \"" + root._remoteDeleteTarget + "\"。\n"
            + "其他协作者将无法再获取该远程分支，但本地同名分支不会被删除。\n"
            + "如需恢复，必须从仍保留该提交的本地仓库重新推送。"
        onConfirmed: {
            if (root._remoteDeleteTarget)
                GitBridge.deleteRemoteBranch(root._remoteDeleteTarget)
            root._remoteDeleteTarget = ""
        }
    }

    // 远程管理面板(添加/修改URL/删除)
    RemoteDialog { id: remoteManageDialog }
}
