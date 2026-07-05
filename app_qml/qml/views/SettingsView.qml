// 设置视图(阶段 1:迁移 setting_interface.py)
// 配置后端映射:主题→ThemeManager,Mica/DPI→ConfigManager,语言→Translator,仓库维护→GitBridge
import QtQuick

import PrismQML as Fluent

Item {
    id: root

    // 更新检查:实际流程(弹框/下载/安装)由主窗口 ToastProgressHost 承载;
    // 本页仅提供手动触发入口 + 短暂的"检查中"按钮态。
    property bool _checking: false
    property string _updateStatus: AppInfo ? ("当前版本 " + AppInfo.version) : ""

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

                // 检查更新:点按钮 → Updater.checkForUpdate();结果(弹框/下载/安装)由主窗口处理
                Fluent.SettingsCard {
                    id: updateCard
                    width: parent ? parent.width : 0
                    title: "检查更新"
                    content: root._updateStatus
                    icon: Fluent.Enums.icon.arrow_sync
                    type: Fluent.Enums.settingCard.type_push
                    buttonText: root._checking ? "检查中…" : "检查更新"
                    enabled: !root._checking
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

    // ==================== 自动更新(仅触发入口)====================
    // 实际流程(发现新版弹框/下载进度/静默安装)由主窗口 ToastProgressHost 承载。
    // 本页只负责手动触发检查 + 维护按钮"检查中"态,结果信号同时被这里(复位按钮)
    // 和主窗口 host(弹框/提示)接收,职责不重叠。
    function _manualCheck() {
        if (!Updater) {
            Fluent.NotificationManager.toast.warning(root, "提示", "更新组件不可用")
            return
        }
        root._checking = true
        root._updateStatus = "正在检查更新…"
        Updater.checkForUpdate()  // 主窗口默认非静默,结果会正常提示
    }

    // 仅复位本页按钮态与状态文字;不弹框、不下载(交给主窗口 host)
    Connections {
        target: typeof Updater !== "undefined" ? Updater : null
        ignoreUnknownSignals: true
        function onUpdateAvailable(version, notes, downloadUrl, htmlUrl) {
            root._checking = false
            root._updateStatus = "发现新版本 " + version
        }
        function onUpToDate(currentVersion) {
            root._checking = false
            root._updateStatus = "已是最新版本 " + currentVersion
        }
        function onCheckFailed(error) {
            root._checking = false
            root._updateStatus = AppInfo ? ("当前版本 " + AppInfo.version) : ""
        }
    }
}
