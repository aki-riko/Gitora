import QtQuick

import PrismQML as Fluent

// 整个分支页面只实例化一个菜单，避免每个虚拟列表 delegate 都创建弹层窗口。
Fluent.MenuCore {
    id: control

    // 与 ButtonDropdown 一致留在宿主场景，避免额外原生窗口和 raise() 开销。
    useInWindowPopup: true

    property string branchName: ""
    property bool isRemoteBranch: false
    property bool isCurrentBranch: false

    signal branchActionRequested(
        string actionText,
        string branchName,
        bool isRemote
    )

    function openFor(anchor, name, isRemote, isCurrent) {
        control.branchName = name
        control.isRemoteBranch = isRemote
        control.isCurrentBranch = isCurrent
        control.openAtControl(anchor)
    }

    onActionTriggered: function(actionText) {
        control.branchActionRequested(
            actionText,
            control.branchName,
            control.isRemoteBranch)
    }

    Fluent.Action {
        text: "合并到当前分支"
        icon: Fluent.Enums.icon.branch_compare
        visible: !control.isRemoteBranch && !control.isCurrentBranch
    }
    Fluent.Action {
        text: "Rebase 到此分支"
        icon: Fluent.Enums.icon.arrow_sync
        visible: !control.isRemoteBranch && !control.isCurrentBranch
    }
    Fluent.MenuSeparator {
        visible: !control.isRemoteBranch && !control.isCurrentBranch
    }
    Fluent.Action {
        text: "设置上游"
        icon: Fluent.Enums.icon.branch_fork_link
        visible: !control.isRemoteBranch
    }
    Fluent.Action {
        text: "重命名"
        icon: Fluent.Enums.icon.rename
        visible: !control.isRemoteBranch
    }
    Fluent.MenuSeparator {
        visible: !control.isRemoteBranch && !control.isCurrentBranch
    }
    Fluent.Action {
        text: "删除分支"
        icon: Fluent.Enums.icon.dismiss_circle
        visible: !control.isRemoteBranch && !control.isCurrentBranch
    }
    Fluent.Action {
        text: "强制删除"
        icon: Fluent.Enums.icon.warning
        visible: !control.isRemoteBranch && !control.isCurrentBranch
    }
    Fluent.Action {
        text: "删除远程分支"
        icon: Fluent.Enums.icon.warning
        visible: control.isRemoteBranch
    }
}
