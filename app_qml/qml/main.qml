// Gitora QML 版主窗口
import QtQuick
import QtQuick.Window

import PrismQML as Fluent
import "components"

QtObject {
    id: root

    readonly property int windowWidth: AppInfo.windowWidth
    readonly property int windowHeight: AppInfo.windowHeight
    readonly property string windowTitle: "Gitora"
    readonly property int settingsPageIndex: pagePaths.length - 1
    readonly property int repositoryTabBarHeight:
        Fluent.Enums.controlSize.tableHeaderHeight + Fluent.Enums.spacing.xxxl

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

    // 可选主线程停顿观测（GITORA_STALL_TRACE=1）：默认关闭，关闭时不建定时器。
    property StallTraceProbe stallTraceProbe: StallTraceProbe {
        enabled: typeof GitoraStallTraceEnabled !== "undefined"
            && GitoraStallTraceEnabled
        intervalMs: typeof GitoraStallTraceIntervalMs !== "undefined"
            ? GitoraStallTraceIntervalMs : 100
        thresholdMs: typeof GitoraStallTraceThresholdMs !== "undefined"
            ? GitoraStallTraceThresholdMs : 250
        gitBridge: typeof GitBridge !== "undefined" ? GitBridge : null
        renderBridge: typeof QmlRenderBridge !== "undefined"
            ? QmlRenderBridge : null
    }

    // 可选崩溃面包屑观测（GITORA_CRASH_TRACE=1）：默认关闭，关闭时 mark() 直接 return。
    // 崩溃后看日志里最后几条 [CRASH_TRACE] 即可还原崩溃前正在做哪类操作。
    property CrashProbe crashProbe: CrashProbe {
        enabled: typeof GitoraCrashTraceEnabled !== "undefined"
            && GitoraCrashTraceEnabled
        renderBridge: typeof QmlRenderBridge !== "undefined"
            ? QmlRenderBridge : null
    }

    // 供各视图共享同一条面包屑通道（视图拿不到 main.qml 的 id）。
    function crashMark(tag, detail) {
        if (root.crashProbe)
            root.crashProbe.mark(tag, detail)
    }

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
            // Windows 的默认属性是页面列表；更新器和 Timer 必须挂在显式属性中，
            // 否则会被 WindowsBar 当作页面重设 parent，异常会中断启动页关闭流程。
            property Item autoUpdaterHost: Item {
                parent: appWindow.contentItem
                anchors.fill: parent

                Fluent.AutoUpdater {
                    id: autoUpdater
                    updater: appUpdater
                    silentArgs: AppInfo ? AppInfo.installerSilentArgs : ""
                }

                Timer {
                    interval: Fluent.Enums.duration.toast
                    running: !GitoraSelftestMode
                    repeat: false
                    onTriggered: autoUpdater.checkSilently()
                }
            }

            width: root.windowWidth; height: root.windowHeight
            windowTitle: root.windowTitle
            windowIcon: typeof AppLogo !== "undefined" ? AppLogo : ""
            windowIconColored: true   // logo.png 是彩色图,跳过单色染色
            // 给全局仓库标签栏预留窗口内容顶部空间；左侧封装导航仍由 PrismQML 管理。
            contentTopMargin: root.repositoryTabBarHeight
            navigationItems: root.navItems
            bottomNavigationItems: root.bottomNavItems
            pageSources: root.pagePaths
            lazyLoading: true
            // 绑定 Mica 开关:让窗口 _micaActive/背景透明 跟随配置(否则开了背景不透明=看不到效果)
            micaEnabled: ConfigManager ? ConfigManager.micaEnabled : false

            // 把"窗口是否可见且未最小化"下发给后端,驱动轮询/标签快照/高级页 Timer 停止。
            // 最小化或隐藏时用户看不到任何刷新结果,继续每秒拉起 git 只是白烧 CPU。
            // 注意:QML 的 Item.visible 是页面可见性,不随窗口最小化变化,故必须用 Window.visibility。
            readonly property bool _windowVisibleNotMinimized:
                visibility !== Window.Minimized && visibility !== Window.Hidden

            function _publishWindowActive() {
                // 面包屑：窗口可见性变化是 QML 绑定信号求值链的最外层常见触发点。
                if (root.crashProbe.enabled) {
                    root.crashProbe.mark("window.visibility",
                        "v=" + visibility + " active=" + _windowVisibleNotMinimized)
                }
                if (typeof GitBridge === "undefined" || !GitBridge) return
                GitBridge.setWindowActive(_windowVisibleNotMinimized)
            }
            onVisibilityChanged: _publishWindowActive()
            property Item repositoryTabBarHost: Item {
                parent: appWindow.contentItem
                anchors.fill: parent
                z: Fluent.Enums.zIndex.controlsAbove

                RepositoryTabBar {
                    anchors.left: parent.left
                    anchors.leftMargin: appWindow.margin
                    anchors.right: parent.right
                    anchors.rightMargin: appWindow.margin
                    anchors.top: parent.top
                    anchors.topMargin: appWindow.margin + appWindow.titleBarHeight
                    height: root.repositoryTabBarHeight
                    gitBridge: typeof GitBridge !== "undefined" ? GitBridge : null
                    repoScanner: typeof RepoScanner !== "undefined" ? RepoScanner : null
                    tabHeight: root.repositoryTabBarHeight
                    switchingEnabled: !!GitBridge && !GitBridge.operationBusy
                        && !!AiCommitBridge && !AiCommitBridge.busy
                        && !!AiCommitPlanBridge && !AiCommitPlanBridge.busy

                    onRepositorySelected: function(path) {
                        // 面包屑：切换仓库会重建页面/模型绑定，是对象生命周期的高危点。
                        root.crashMark("repo.select", "")
                        if (GitBridge && path !== GitBridge.repoPath)
                            GitBridge.openRepoAsync(path)
                    }
                }
            }
            Component.onCompleted: {
                root.toastProgressHostInstance = root.toastProgressHostComponent.createObject(this.contentItem)
                let currentWindow = this
                Qt.callLater(function() { root.applyNativeWindowIcon(currentWindow) })
                // 首帧时 visibility 可能还没就绪，延后一拍再下发一次。
                Qt.callLater(function() { appWindow._publishWindowActive() })
            }
            // 面包屑：页面切换会触发页面栈/懒加载覆盖层重建，是绑定生命周期的高危点。
            onCurrentIndexChanged: root.crashMark("page.switch",
                "index=" + currentIndex)

        }
    }

    property Component toastProgressHostComponent: Component {
        ToastProgressHost {}
    }
}
