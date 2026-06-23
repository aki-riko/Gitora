// 设置视图(阶段 1:迁移 setting_interface.py)
// 配置后端映射:主题→ThemeManager,Mica/DPI→ConfigManager,语言→Translator,仓库维护→GitBridge
import QtQuick

import FluentQML as Fluent

Item {
    id: root

    // 更新检查状态
    property bool _checking: false       // 正在检查
    property bool _downloading: false    // 正在下载
    property bool _manualTriggered: false // 本次检查是否手动触发(决定"已最新/失败"是否提示)
    property string _updateStatus: AppInfo ? ("当前版本 " + AppInfo.version) : ""
    property string _pendingDownloadUrl: "" // 待下载的安装包地址
    property string _pendingHtmlUrl: ""     // 新版 Releases 页(下载失败兜底跳转)

    Fluent.ScrollArea {
        anchors.fill: parent

        Column {
            id: contentCol
            width: parent ? parent.width : 0
            spacing: Fluent.Enums.spacing.xl
            topPadding: Fluent.Enums.spacing.xl
            bottomPadding: Fluent.Enums.spacing.xl
            leftPadding: sidePad
            rightPadding: sidePad
            property real sidePad: Math.max(Fluent.Enums.spacing.xxl, (width - 980) / 2)

            readonly property real groupWidth: width - sidePad * 2

            // 页面标题
            Text {
                text: "设置"
                font.pixelSize: Fluent.Enums.typography.displayLarge
                font.bold: true
                color: Fluent.Enums.textColor.primary
                font.family: Fluent.Enums.fontFamily
            }

            // ==================== 仓库维护 ====================
            Fluent.SettingsCardGroup {
                title: "仓库维护"
                width: contentCol.groupWidth

                Fluent.SettingsCard {
                    width: parent ? parent.width : 0
                    title: "清理未跟踪文件"
                    content: "删除所有未被 Git 跟踪的文件和目录"
                    icon: Fluent.Enums.icon.icon_delete
                    type: Fluent.Enums.settingCard.type_push
                    buttonText: "清理文件"
                    onClicked: root._cleanFiles()
                }

                Fluent.SettingsCard {
                    width: parent ? parent.width : 0
                    title: "优化仓库"
                    content: "运行垃圾回收,优化仓库性能"
                    icon: Fluent.Enums.icon.broom
                    type: Fluent.Enums.settingCard.type_push
                    buttonText: "垃圾回收"
                    onClicked: root._runGc()
                }
            }

            // ==================== 个性化 ====================
            Fluent.SettingsCardGroup {
                title: "个性化"
                width: contentCol.groupWidth

                // 应用主题
                Fluent.SettingsCard {
                    width: parent ? parent.width : 0
                    title: "应用主题"
                    content: "调整应用的外观"
                    icon: Fluent.Enums.icon.dark_theme
                    type: Fluent.Enums.settingCard.type_combobox
                    model: ["跟随系统", "浅色", "深色"]
                    property var themeValues: ["auto", "light", "dark"]
                    Component.onCompleted: {
                        if (ThemeManager) {
                            var idx = themeValues.indexOf(ThemeManager.theme)
                            currentIndex = idx >= 0 ? idx : 0
                        }
                    }
                    onIndexSelected: function(idx) {
                        if (ThemeManager && idx >= 0)
                            ThemeManager.setThemeFromQml(themeValues[idx])
                    }
                }

                // 云母效果
                Fluent.SettingsCard {
                    width: parent ? parent.width : 0
                    title: "云母效果"
                    content: "为窗口和表面应用半透明效果(仅 Windows 11)"
                    icon: Fluent.Enums.icon.blur
                    type: Fluent.Enums.settingCard.type_switch
                    checked: ConfigManager ? ConfigManager.micaEnabled : false
                    onSwitchToggled: function(isChecked) {
                        if (ConfigManager) ConfigManager.setMicaEnabled(isChecked)
                    }
                }

                // 语言
                Fluent.SettingsCard {
                    width: parent ? parent.width : 0
                    title: "界面语言"
                    content: "设置界面显示语言"
                    icon: Fluent.Enums.icon.local_language
                    type: Fluent.Enums.settingCard.type_combobox
                    model: ["简体中文", "繁體中文", "English", "跟随系统"]
                    property var langValues: ["zh_CN", "zh_TW", "en", "auto"]
                    Component.onCompleted: {
                        var idx = langValues.indexOf(Fluent.Translator.language)
                        currentIndex = idx >= 0 ? idx : 3
                    }
                    onIndexSelected: function(idx) {
                        if (idx >= 0) Fluent.Translator.setLanguage(langValues[idx])
                    }
                }
            }

            // ==================== 关于 ====================
            Fluent.SettingsCardGroup {
                title: "关于"
                width: contentCol.groupWidth

                Fluent.SettingsCard {
                    width: parent ? parent.width : 0
                    title: "关于 Gitora"
                    content: AppInfo ? ("版本 " + AppInfo.version + " · © " + AppInfo.year + " " + AppInfo.author) : ""
                    icon: Fluent.Enums.icon.info
                    // 有项目地址才显示超链接,否则用普通按钮卡片(无按钮文字=纯展示)
                    type: (AppInfo && AppInfo.helpUrl !== "") ? Fluent.Enums.settingCard.type_hyperlink : Fluent.Enums.settingCard.type_push
                    url: AppInfo ? AppInfo.helpUrl : ""
                    linkText: "项目主页"
                    buttonText: ""
                }

                // 检查更新:点按钮 → Updater.checkForUpdate(),结果经下方 Connections 处理
                Fluent.SettingsCard {
                    id: updateCard
                    width: parent ? parent.width : 0
                    title: "检查更新"
                    content: root._updateStatus
                    icon: Fluent.Enums.icon.arrow_sync
                    type: Fluent.Enums.settingCard.type_push
                    buttonText: root._checking ? "检查中…" : "检查更新"
                    enabled: !root._checking && !root._downloading
                    onClicked: root._manualCheck()
                }
            }
        }
    }

    // ==================== 操作 ====================
    function _cleanFiles() {
        if (!GitBridge || !GitBridge.repoPath) {
            Fluent.NotificationManager.toast.warning(root, "提示", "请先打开一个 Git 仓库")
            return
        }
        var res = GitBridge.clean(true)
        if (res[0]) Fluent.NotificationManager.toast.success(root, "清理完成", res[1] || "")
        else Fluent.NotificationManager.toast.error(root, "清理失败", res[1] || "")
    }

    function _runGc() {
        if (!GitBridge || !GitBridge.repoPath) {
            Fluent.NotificationManager.toast.warning(root, "提示", "请先打开一个 Git 仓库")
            return
        }
        GitBridge.gc()  // 异步,结果经 operationFinished 反馈(由全局监听统一弹 toast,避免重复)
    }

    // ==================== 自动更新 ====================
    // 发现新版本时的确认对话框
    Fluent.ConfirmDialog {
        id: updateConfirmDialog
        level: Fluent.Enums.statusLevel.attention
        title: "发现新版本"
        confirmText: "下载并安装"
        cancelText: "稍后"
        onConfirmed: {
            if (root._pendingDownloadUrl !== "") {
                root._startDownload(root._pendingDownloadUrl)
            } else if (root._pendingHtmlUrl !== "" && Updater) {
                // 没有可下载的安装包资源,退而打开 Releases 页让用户手动下载
                Updater.openInBrowser(root._pendingHtmlUrl)
            }
        }
    }

    // 下载进度对话框(无限转圈 + 百分比文字)
    Fluent.ProgressDialog {
        id: downloadDialog
        title: "正在下载更新"
        content: "准备中…"
    }

    // 接收 Updater 信号
    Connections {
        target: Updater
        ignoreUnknownSignals: true

        function onUpdateAvailable(version, notes, downloadUrl, htmlUrl) {
            root._checking = false
            root._updateStatus = "发现新版本 " + version
            root._pendingDownloadUrl = downloadUrl
            root._pendingHtmlUrl = htmlUrl
            var msg = "新版本 " + version + " 可用,当前 " + (AppInfo ? AppInfo.version : "") + "。"
            if (notes && notes.length > 0) {
                var brief = notes.length > 300 ? notes.substring(0, 300) + "…" : notes
                msg += "\n\n更新说明:\n" + brief
            }
            updateConfirmDialog.message = msg
            updateConfirmDialog.open()
        }

        function onUpToDate(currentVersion) {
            root._checking = false
            root._updateStatus = "已是最新版本 " + currentVersion
            // 只有手动触发才提示;启动静默检查保持安静
            if (root._manualTriggered)
                Fluent.NotificationManager.toast.success(root, "已是最新", "当前已是最新版本 " + currentVersion)
        }

        function onCheckFailed(error) {
            root._checking = false
            root._updateStatus = AppInfo ? ("当前版本 " + AppInfo.version) : ""
            if (root._manualTriggered)
                Fluent.NotificationManager.toast.error(root, "检查更新失败", error || "网络错误")
        }

        function onDownloadProgress(received, total) {
            if (total > 0) {
                var pct = Math.floor(received * 100 / total)
                downloadDialog.content = pct + "%  (" + root._fmtSize(received) + " / " + root._fmtSize(total) + ")"
            } else {
                downloadDialog.content = root._fmtSize(received) + " 已下载"
            }
        }

        function onDownloadFinished(localPath) {
            root._downloading = false
            downloadDialog.accept()
            // 启动静默安装并退出应用(安装包覆盖文件后自动重启 Gitora)
            var args = AppInfo ? AppInfo.installerSilentArgs : ""
            var ok = Updater.runInstallerAndQuit(localPath, args)
            if (!ok)
                Fluent.NotificationManager.toast.error(root, "安装失败", "无法启动安装程序,请手动安装")
        }

        function onDownloadFailed(error) {
            root._downloading = false
            downloadDialog.reject()
            root._updateStatus = "下载失败"
            // 下载失败时,提供打开 Releases 页手动下载的兜底
            Fluent.NotificationManager.toast.error(root, "下载失败", (error || "网络错误") + ",可前往项目主页手动下载")
            if (root._pendingHtmlUrl !== "" && Updater)
                Updater.openInBrowser(root._pendingHtmlUrl)
        }
    }

    function _manualCheck() {
        if (!Updater) {
            Fluent.NotificationManager.toast.warning(root, "提示", "更新组件不可用")
            return
        }
        root._manualTriggered = true
        root._checking = true
        root._updateStatus = "正在检查更新…"
        Updater.checkForUpdate()
    }

    function _startDownload(url) {
        if (!Updater) return
        root._downloading = true
        downloadDialog.content = "准备中…"
        downloadDialog.open()
        Updater.downloadUpdate(url)
    }

    // 字节数转人类可读(KB/MB)
    function _fmtSize(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + " MB"
        if (bytes >= 1024) return (bytes / 1024).toFixed(0) + " KB"
        return bytes + " B"
    }
}
