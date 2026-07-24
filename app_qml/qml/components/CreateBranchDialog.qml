import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dialog

    // MessageBox 自带标题与调用方表单是并列子项，直接同时使用会从同一坐标绘制。
    // 统一把可见标题和表单放进一个布局，继续复用引擎的遮罩、动画和操作按钮。
    title: ""
    confirmText: checkoutCheck.checked ? "创建并切换" : "创建"
    cancelText: "取消"

    function openFor(startPoint, checkoutAfterCreate) {
        branchNameInput.text = ""
        startPointInput.text = String(startPoint || "HEAD")
        checkoutCheck.checked = Boolean(checkoutAfterCreate)
        dialog.open()
        Qt.callLater(function() { branchNameInput.forceActiveFocus() })
    }

    function validate() {
        return branchNameInput.text.trim().length > 0
            && startPointInput.text.trim().length > 0
    }

    ColumnLayout {
        width: 360
        spacing: Fluent.Enums.spacing.m

        Fluent.Label {
            objectName: "createBranchDialogTitle"
            Layout.fillWidth: true
            text: "新建分支"
            type: Fluent.Enums.label.type_subtitle
            color: Fluent.Enums.textColor.primary
        }

        Fluent.Label {
            objectName: "createBranchNameLabel"
            Layout.fillWidth: true
            text: "分支名称"
            type: Fluent.Enums.label.type_body_strong
            color: Fluent.Enums.textColor.secondary
        }

        Fluent.LineEdit {
            id: branchNameInput
            objectName: "createBranchNameInput"
            Layout.fillWidth: true
            placeholderText: "如 feature/new-ui"
        }

        Fluent.Label {
            objectName: "createBranchStartPointLabel"
            Layout.fillWidth: true
            text: "创建起点"
            type: Fluent.Enums.label.type_body_strong
            color: Fluent.Enums.textColor.secondary
        }

        Fluent.LineEdit {
            id: startPointInput
            objectName: "createBranchStartPointInput"
            Layout.fillWidth: true
            placeholderText: "提交哈希、分支或标签（默认 HEAD）"
        }

        Text {
            objectName: "createBranchBehaviorHint"
            Layout.fillWidth: true
            text: "不切换时只创建引用，不会改动当前分支或工作区。"
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            wrapMode: Text.WordWrap
        }

        Fluent.CheckBox {
            id: checkoutCheck
            objectName: "createBranchCheckoutCheck"
            Layout.fillWidth: true
            text: "创建后切换到新分支"
            checked: false
        }
    }

    onAccepted: {
        var result = GitBridge.createBranchAt(
            branchNameInput.text.trim(),
            startPointInput.text.trim(),
            checkoutCheck.checked)
        if (result[0])
            Fluent.NotificationManager.desktop.success("成功", result[1] || "分支已创建")
        else
            Fluent.NotificationManager.desktop.error("无法创建分支", result[1] || "创建分支失败")
    }
}
