// 主窗口级耗时操作桌面进度通知承载
import QtQuick

import PrismQML as Fluent

Item {
    id: root

    anchors.fill: parent

    property var _gitToast: null
    property var _downloadToast: null
    property bool _updateSilent: false
    property string _downloadUrl: ""
    property string _htmlUrl: ""

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

    function _trackDownloadToast(toast) {
        if (!toast) return null
        toast.duration = 0
        toast.closed.connect(function() {
            if (root._downloadToast === toast) root._downloadToast = null
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

    function _ensureDownloadToast(determinate, title, message) {
        var feature = determinate
            ? Fluent.Enums.notification.feature_progress_ring
            : Fluent.Enums.notification.feature_indeterminate_ring
        var toast = root._downloadToast
        if (!toast || !toast.visible) {
            toast = root._createProgressNotification(title, message, feature)
            root._downloadToast = root._trackDownloadToast(toast)
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

    function _finishProgressToast(toast, isDownloadToast, ok, title, message) {
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
            if (isDownloadToast) root._downloadToast = null
            else root._gitToast = null
            _showResult(false, title, message)
        }
    }

    function checkForUpdate(silent) {
        if (!Updater) return
        root._updateSilent = silent === true
        Updater.checkForUpdate()
    }

    function _startDownload(url) {
        if (!Updater) return
        var toast = _ensureDownloadToast(false, "正在下载更新", "准备中")
        if (toast) toast.progress = 0
        Updater.downloadUpdate(url)
    }

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

    function _fmtSize(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB"
        if (bytes >= 1024) return (bytes / 1024).toFixed(0) + " KB"
        return bytes + " B"
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
            root._finishProgressToast(
                root._gitToast,
                false,
                ok,
                ok ? "操作完成" : "操作失败",
                msg || (ok ? "操作完成" : "操作失败")
            )
        }
    }

    Fluent.UpdateDialog {
        id: updateConfirmDialog

        onConfirmed: {
            if (root._downloadUrl !== "") {
                root._startDownload(root._downloadUrl)
            } else if (root._htmlUrl !== "" && Updater) {
                Updater.openInBrowser(root._htmlUrl)
            }
        }
    }

    Connections {
        target: typeof Updater !== "undefined" ? Updater : null
        ignoreUnknownSignals: true

        function onUpdateAvailable(version, notes, downloadUrl, htmlUrl) {
            root._downloadUrl = downloadUrl
            root._htmlUrl = htmlUrl
            updateConfirmDialog.version = version
            updateConfirmDialog.currentVersion = AppInfo ? AppInfo.version : ""
            updateConfirmDialog.notes = notes || ""
            updateConfirmDialog.open()
            root._updateSilent = false
        }

        function onUpToDate(currentVersion) {
            if (!root._updateSilent)
                Fluent.NotificationManager.desktop.success("已是最新", "当前已是最新版本 " + currentVersion)
            root._updateSilent = false
        }

        function onCheckFailed(error) {
            if (!root._updateSilent)
                Fluent.NotificationManager.desktop.error("检查更新失败", error || "网络错误")
            root._updateSilent = false
        }

        function onDownloadProgress(received, total) {
            if (total > 0) {
                var pct = root._clampProgress(received / total)
                var toast = root._ensureDownloadToast(
                    true,
                    "正在下载更新",
                    Math.round(pct * 100) + "%  (" + root._fmtSize(received) + " / " + root._fmtSize(total) + ")"
                )
                if (toast) toast.progress = pct
            } else {
                root._ensureDownloadToast(false, "正在下载更新", root._fmtSize(received) + " 已下载")
            }
        }

        function onDownloadFinished(localPath) {
            root._finishProgressToast(root._downloadToast, true, true, "下载完成", "正在启动安装程序")
            var args = AppInfo ? AppInfo.installerSilentArgs : ""
            var ok = Updater.runInstallerAndQuit(localPath, args)
            if (!ok)
                Fluent.NotificationManager.desktop.warning("安装未开始", "已取消或需要管理员权限,安装包已下载到临时目录,可手动运行")
        }

        function onDownloadFailed(error) {
            var message = (error || "网络错误") + ",可前往项目主页手动下载"
            root._finishProgressToast(root._downloadToast, true, false, "下载失败", message)
            if (root._htmlUrl !== "" && Updater)
                Updater.openInBrowser(root._htmlUrl)
        }
    }

    Timer {
        interval: Fluent.Enums.duration.toast
        running: true
        repeat: false
        onTriggered: root.checkForUpdate(true)
    }
}
