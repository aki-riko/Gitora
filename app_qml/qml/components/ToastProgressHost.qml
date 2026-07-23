// Main-window Git and AI progress notification host 主窗口 Git 与 AI 进度通知承载
import QtQuick

import PrismQML as Fluent

Item {
    id: root

    property var _gitToast: null

    function _clampProgress(value) {
        return Math.max(0, Math.min(1, value))
    }

    function _normalizeTitle(text, fallback) {
        var title = (text || fallback || "正在处理").toString()
        while (title.length > 0) {
            var tail = title.charAt(title.length - 1)
            if (tail !== "." && tail !== "…") break
            title = title.slice(0, -1)
        }
        return title
    }

    function _syncToastText(toast, title, message) {
        if (!toast) return
        toast.title = title || ""
        toast.message = message || ""
        toast.orient = toast.message.indexOf("\n") >= 0 || toast.message.length > 60
            ? Qt.Vertical : Qt.Horizontal
    }

    function _trackGitToast(toast) {
        if (!toast) return null
        toast.duration = 0
        toast.closed.connect(function() {
            if (root._gitToast === toast) root._gitToast = null
        })
        return toast
    }

    function _createProgressNotification(title, message, feature) {
        return Fluent.NotificationManager.desktop.info(
            title,
            message,
            0,
            undefined,
            {
                "feature": feature,
                "progress": 0
            }
        )
    }

    function _ensureGitToast(determinate, title, message) {
        var feature = determinate
            ? Fluent.Enums.notification.feature_progress_ring
            : Fluent.Enums.notification.feature_indeterminate_ring
        var toast = root._gitToast
        if (!toast || !toast.visible) {
            toast = root._createProgressNotification(title, message, feature)
            root._gitToast = root._trackGitToast(toast)
        }
        if (!toast) return null
        toast.severity = "processing"
        toast.feature = feature
        toast.duration = 0
        _syncToastText(toast, title, message)
        return toast
    }

    function _showResult(ok, title, message) {
        if (ok)
            Fluent.NotificationManager.desktop.success(title, message || "")
        else
            Fluent.NotificationManager.desktop.error(title, message || "")
    }

    function _finishGitProgressToast(toast, ok, title, message) {
        if (!toast || !toast.visible) {
            _showResult(ok, title, message)
            return
        }
        if (ok) {
            toast.severity = "success"
            toast.feature = Fluent.Enums.notification.feature_progress_ring
            toast.progress = 1
            _syncToastText(toast, title, message)
        } else {
            toast.hide()
            root._gitToast = null
            _showResult(false, title, message)
        }
    }

    anchors.fill: parent

    Connections {
        target: AiCommitBridge

        function onErrorOccurred(message) {
            Fluent.NotificationManager.desktop.error("AI 提交规划", message)
        }

        function onConnectionTestFinished(ok, message) {
            root._showResult(ok, ok ? "连接检测" : "连接失败", message)
        }

        function onModelListFinished(provider, ok, models, message) {
            root._showResult(ok, ok ? "模型列表" : "获取失败", message)
        }
    }

    Connections {
        target: AiCommitPlanBridge

        function onErrorOccurred(message) {
            Fluent.NotificationManager.desktop.error("AI 提交规划", message)
        }

        function onPlanCommitPushFinished(ok, message) {
            root._showResult(
                ok,
                ok ? "AI 提交完成" : "AI 提交未完成",
                message
            )
        }
    }

    Connections {
        target: GitBridge

        function onOperationStarted(message) {
            var title = root._normalizeTitle(message, "正在执行 Git 操作")
            var toast = root._ensureGitToast(false, title, "请稍候")
            if (toast) toast.progress = 0
        }

        function onProgressUpdated(percent, message) {
            var pct = root._clampProgress(percent / 100)
            var title = "正在执行 Git 操作"
            var body = (message || "处理中") + "  " + Math.round(pct * 100) + "%"
            var toast = root._ensureGitToast(true, title, body)
            if (toast) toast.progress = pct
        }

        function onOperationFinished(ok, msg) {
            root._finishGitProgressToast(
                root._gitToast,
                ok,
                ok ? "操作完成" : "操作失败",
                msg || (ok ? "操作完成" : "操作失败")
            )
        }
    }
}
