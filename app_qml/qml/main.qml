// Gitess QML 版主窗口(阶段 0 脚手架)
import QtQuick

import FluentQML as Fluent

QtObject {
    id: root

    readonly property int windowWidth: 1100
    readonly property int windowHeight: 720
    readonly property string windowTitle: "Gitess"

    function iconPath(name) {
        return (typeof FluentIconsDir !== "undefined" ? FluentIconsDir : "") + name + ".svg"
    }

    property var navItems: [
        { "text": "仓库", "icon": iconPath("Folder") },
        { "text": "历史", "icon": iconPath("History") },
        { "text": "分支", "icon": iconPath("BranchFork") }
    ]

    property var bottomNavItems: [
        { "text": "设置", "icon": iconPath("Settings"), "key": "SettingsPage" }
    ]

    property var pagePaths: [
        Qt.resolvedUrl("views/RepoView.qml"),
        Qt.resolvedUrl("views/HistoryView.qml"),
        Qt.resolvedUrl("views/PlaceholderView.qml"),
        Qt.resolvedUrl("views/SettingsView.qml")
    ]

    property var windowInstance: null

    Component.onCompleted: {
        Fluent.Translator.setLanguage(Fluent.Enums.lang.zh_CN)
        windowInstance = windowComponent.createObject(null)
    }
    Component.onDestruction: { if (windowInstance) windowInstance.destroy() }

    property Component windowComponent: Component {
        Fluent.Windows {
            width: root.windowWidth; height: root.windowHeight
            windowTitle: root.windowTitle
            navigationItems: root.navItems
            bottomNavigationItems: root.bottomNavItems
            pageSources: root.pagePaths
            lazyLoading: false
        }
    }
}
