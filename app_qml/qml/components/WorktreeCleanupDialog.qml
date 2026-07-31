// 游离工作树批量清理预览与确认对话框。
import QtQuick
import QtQuick.Layouts

import PrismQML as Fluent

Fluent.MessageBox {
    id: dlg

    title: ""
    confirmText: _loading ? "正在检查..."
        : (_remaining > 0 ? ("请等待 (" + _remaining + "s)") : "确认移除")
    cancelText: "取消"
    yesButtonVisible: !_loading && removableModel.count > 0
    property int countdown: 3
    property int _remaining: 0
    property int _requestSerial: 0
    property string _requestRepoPath: ""
    property bool _loading: false
    ListModel { id: removableModel }
    ListModel { id: skippedModel }

    function clearPreview() {
        removableModel.clear()
        skippedModel.clear()
        dlg._requestRepoPath = ""
        dlg._remaining = 0
        dlg._loading = false
        countdownTimer.stop()
    }

    function openPreview() {
        if (!GitBridge || !GitBridge.repoPath) return
        clearPreview()
        dlg._requestSerial++
        var requestSerial = dlg._requestSerial
        dlg._requestRepoPath = GitBridge.repoPath
        dlg._loading = true
        dlg.open()
        var task = GitBridge.previewDetachedWorktreeCleanup()
        task.succeeded.connect(function(preview) {
            if (requestSerial !== dlg._requestSerial || !preview || !GitBridge
                    || preview.repoPath !== GitBridge.repoPath
                    || preview.repoPath !== dlg._requestRepoPath) return
            if (!preview.ok) {
                dlg.close()
                Fluent.NotificationManager.desktop.error(
                    "无法预览", preview.message || "读取游离工作树失败")
                return
            }
            dlg._loading = false
            for (var i = 0; i < preview.removable.length; i++)
                removableModel.append({ "path": preview.removable[i] })
            for (var j = 0; j < preview.skipped.length; j++)
                skippedModel.append(preview.skipped[j])
            dlg._remaining = removableModel.count > 0 ? dlg.countdown : 0
            if (dlg._remaining > 0) countdownTimer.restart()
        })
        task.failed.connect(function() {
            if (requestSerial !== dlg._requestSerial) return
            dlg.close()
            Fluent.NotificationManager.desktop.error(
                "无法预览", "读取游离工作树失败")
        })
    }

    function validate() {
        return dlg._remaining <= 0 && removableModel.count > 0
    }

    onAccepted: {
        var paths = []
        for (var i = 0; i < removableModel.count; i++)
            paths.push(removableModel.get(i).path)
        if (paths.length > 0) GitBridge.removeDetachedWorktrees(paths)
        clearPreview()
    }

    onRejected: clearPreview()

    Connections {
        target: GitBridge
        function onRepoPathChanged(path) {
            dlg._requestSerial++
            if (dlg.visible) dlg.close()
            dlg.clearPreview()
        }
    }

    Timer {
        id: countdownTimer
        interval: 1000
        repeat: true
        onTriggered: {
            dlg._remaining--
            if (dlg._remaining <= 0) stop()
        }
    }

    ColumnLayout {
        width: 520
        spacing: Fluent.Enums.spacing.m

        DialogTitle {
            text: "确认清理游离工作树"
        }

        Text {
            Layout.fillWidth: true
            text: dlg._loading ? "正在检查游离工作树状态，请稍候..."
                : (removableModel.count > 0
                ? ("以下 " + removableModel.count
                   + " 个目录当前干净，确认后将移除；预览后新增的改动仍会被跳过。")
                : "没有可直接移除的干净游离工作树。")
            color: Fluent.Enums.statusLevel.warningColor
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            wrapMode: Text.WordWrap
        }

        Fluent.ScrollArea {
            id: removableList
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(
                removableModel.count * itemHeight + Fluent.Enums.spacing.m, 220)
            visible: removableModel.count > 0
            type: Fluent.Enums.scroll.type_list
            itemHeight: Fluent.Enums.typography.caption + Fluent.Enums.spacing.l
            reuseItems: true
            bounceEnabled: false
            padding: 0
            model: removableModel
            delegate: Text {
                width: ListView.view ? ListView.view.width : 0
                height: removableList.itemHeight
                text: model.path
                color: Fluent.Enums.textColor.secondary
                font.family: "Consolas, monospace"
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideMiddle
                verticalAlignment: Text.AlignVCenter
            }
        }

        Text {
            Layout.fillWidth: true
            visible: skippedModel.count > 0
            text: "以下 " + skippedModel.count
                + " 个目录会跳过（有改动、已锁定、已失效或状态读取失败）："
            color: Fluent.Enums.textColor.tertiary
            font.family: Fluent.Enums.fontFamily
            font.pixelSize: Fluent.Enums.typography.caption
            wrapMode: Text.WordWrap
        }

        Fluent.ScrollArea {
            id: skippedList
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(
                skippedModel.count * itemHeight + Fluent.Enums.spacing.m, 160)
            visible: skippedModel.count > 0
            type: Fluent.Enums.scroll.type_list
            itemHeight: Fluent.Enums.typography.caption + Fluent.Enums.spacing.l
            reuseItems: true
            bounceEnabled: false
            padding: 0
            model: skippedModel
            delegate: Text {
                width: ListView.view ? ListView.view.width : 0
                height: skippedList.itemHeight
                text: model.path + " — " + model.reason
                color: Fluent.Enums.textColor.tertiary
                font.family: "Consolas, monospace"
                font.pixelSize: Fluent.Enums.typography.caption
                elide: Text.ElideMiddle
                verticalAlignment: Text.AlignVCenter
            }
        }
    }
}
