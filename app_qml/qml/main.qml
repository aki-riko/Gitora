// Gitora QML 版主窗口
import QtQuick
import QtQuick.Window

import PrismQML as Fluent
import "components"

QtObject {
    id: root

    readonly property int windowWidth: 1100
    readonly property int windowHeight: 720
    readonly property string windowTitle: "Gitora"
    readonly property int settingsPageIndex: pagePaths.length - 1

    function iconPath(name) {
        return (typeof FluentIconsDir !== "undefined" ? FluentIconsDir : "") + name + ".svg"
    }

    property var navItems: [
        { "text": "仓库", "icon": iconPath("Folder") },
        { "text": "历史", "icon": iconPath("History") },
        { "text": "分支", "icon": iconPath("BranchFork") },
        { "text": "标签", "icon": iconPath("Tag") },
        { "text": "暂存", "icon": iconPath("Archive") },
        { "text": "冲突", "icon": iconPath("Warning") },
        { "text": "高级", "icon": iconPath("BranchFork") }
    ]

    property var bottomNavItems: [
        { "text": "设置", "icon": iconPath("Settings"), "key": "SettingsView" }
    ]

    property var pagePaths: [
        Qt.resolvedUrl("views/RepoView.qml"),
        Qt.resolvedUrl("views/HistoryView.qml"),
        Qt.resolvedUrl("views/BranchView.qml"),
        Qt.resolvedUrl("views/TagView.qml"),
        Qt.resolvedUrl("views/StashView.qml"),
        Qt.resolvedUrl("views/ConflictView.qml"),
        Qt.resolvedUrl("views/AdvancedView.qml"),
        Qt.resolvedUrl("views/SettingsView.qml")
    ]

    property var windowInstance: null
    property var toastProgressHostInstance: null

    function applyNativeWindowIcon(targetWindow) {
        if (!targetWindow || typeof WindowIconBridge === "undefined") return
        let iconSource = (typeof AppIconFile !== "undefined" && AppIconFile !== "") ? AppIconFile : targetWindow.windowIcon
        if (iconSource) WindowIconBridge.applyWindowIcon(targetWindow, iconSource)
    }

    // 供 Python 侧单实例 IPC 调用:把窗口提到前台(第二实例启动时激活已有窗口)
    function activateWindow() {
        if (!windowInstance) return
        if (windowInstance.visibility === Window.Minimized || windowInstance.visibility === Window.Hidden)
            windowInstance.showNormal()
        else
            windowInstance.show()
        windowInstance.raise()
        windowInstance.requestActivate()
    }

    Component.onCompleted: {
        Fluent.Translator.setLanguage(Fluent.Enums.lang.zh_CN)
        windowInstance = windowComponent.createObject(null)
    }
    Component.onDestruction: { if (windowInstance) windowInstance.destroy() }

    property Component windowComponent: Component {
        Fluent.Windows {
            id: appWindow

            readonly property var autoUpdaterController: autoUpdater

            width: root.windowWidth; height: root.windowHeight
            windowTitle: root.windowTitle
            windowIcon: typeof AppLogo !== "undefined" ? AppLogo : ""
            windowIconColored: true   // logo.png 是彩色图,跳过单色染色
            navigationItems: root.navItems
            bottomNavigationItems: root.bottomNavItems
            pageSources: root.pagePaths
            lazyLoading: true
            // 绑定 Mica 开关:让窗口 _micaActive/背景透明 跟随配置(否则开了背景不透明=看不到效果)
            micaEnabled: ConfigManager ? ConfigManager.micaEnabled : false
            // 创建启动屏幕,赋给 _splashInstance;内容加载完成后引擎自动 finish()
            Component.onCompleted: {
                this._splashInstance = root.splashComponent.createObject(this.contentItem)
                root.toastProgressHostInstance = root.toastProgressHostComponent.createObject(this.contentItem)
                let currentWindow = this
                Qt.callLater(function() { root.applyNativeWindowIcon(currentWindow) })
            }

            Fluent.AutoUpdater {
                id: autoUpdater
                updater: appUpdater
                silentArgs: AppInfo ? AppInfo.installerSilentArgs : ""
            }

            Timer {
                interval: Fluent.Enums.duration.toast
                running: true
                repeat: false
                onTriggered: {
                    autoUpdater.notifyWhenUpToDate = false
                    autoUpdater.check()
                }
            }
        }
    }

    // 启动屏幕
    property Component splashComponent: Component {
        Fluent.SplashScreen {
            iconSource: typeof AppLogo !== "undefined" ? AppLogo : ""
            title: root.windowTitle
            subtitle: "正在加载..."
            z: 9999
        }
    }

    property Component toastProgressHostComponent: Component {
        ToastProgressHost {}
    }
}
