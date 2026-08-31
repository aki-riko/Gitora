# coding: utf-8
"""仓库标签栏的最小 QML 加载与模型行为测试。"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = ROOT / "app_qml" / "qml" / "components"


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


class _DummyGitBridge:
    def __init__(self, repo_path: str) -> None:
        from PySide6.QtCore import QObject, Property, Signal, Slot

        class Bridge(QObject):
            repoPathChanged = Signal(str)
            repoOpened = Signal(bool, str)
            repoOpenRejected = Signal(str, str)
            statusChanged = Signal()
            statusReady = Signal(str, int)
            branchReady = Signal(str, str)

            def __init__(self, path: str) -> None:
                super().__init__()
                self._repo_path = path

            def _get_repo_path(self) -> str:
                return self._repo_path

            @Slot(result="QVariantList")
            def getRecentRepos(self) -> list[str]:
                return ["D:/Repos/PrismQML", "D:/Repos/Kaleidos"]

            @Slot()
            def requestStatus(self) -> None:
                return None

            repoPath = Property(str, _get_repo_path, notify=repoPathChanged)

        self.object = Bridge(repo_path)


class _DummyRepoScanner:
    def __init__(self) -> None:
        from PySide6.QtCore import QObject, Property, Signal, Slot

        class Scanner(QObject):
            scanFinished = Signal(int)

            def _get_scanning(self) -> bool:
                return False

            @Slot("QVariantList", result="QVariantList")
            def mergeWithOpenedRepos(self, opened: list[str]) -> list[str]:
                return list(opened or [])

            scanning = Property(bool, _get_scanning, constant=True)

        self.object = Scanner()


def _probe_source() -> bytes:
    component_url = COMPONENT_DIR.as_uri()
    return f"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import \"{component_url}\"

Window {{
    width: 900
    height: 148
    visible: false

    RepositoryTabBar {{
        id: bar
        objectName: \"repositoryTabBar\"
        x: 0
        y: 0
        width: 900
        height: 68
        tabHeight: Fluent.Enums.controlSize.tableHeaderHeight + Fluent.Enums.spacing.xxxl
        gitBridge: bridge
        repoScanner: scanner
    }}
}}
""".encode("utf-8")


def _create_repository_scene():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from prismqml import qml_path

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(qml_path().parent))

    bridge = _DummyGitBridge("D:/Repos/Gitora")
    scanner = _DummyRepoScanner()
    context = engine.rootContext()
    context.setContextProperty("bridge", bridge.object)
    context.setContextProperty("scanner", scanner.object)

    component = QQmlComponent(engine)
    component.setData(
        _probe_source(),
        QUrl.fromLocalFile(str(ROOT / "tests" / "RepositoryTabBarProbe.qml")),
    )
    deadline = time.monotonic() + 2
    while component.status() == QQmlComponent.Status.Loading and time.monotonic() < deadline:
        _pump(20)
    assert component.status() == QQmlComponent.Status.Ready, component.errors()
    window = component.create()
    assert window is not None, component.errors()
    _pump(20)
    return app, engine, component, window, bridge


def _destroy_repository_scene(app, engine, component, window) -> None:
    window.destroy()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()


def test_repository_tab_bar_loads_and_deduplicates() -> None:
    app, engine, component, window, bridge = _create_repository_scene()

    from PySide6.QtCore import QObject

    bar = window.findChild(QObject, "repositoryTabBar")
    fluent_bar = window.findChild(QObject, "repositoryFluentTabBar")
    assert bar is not None
    assert fluent_bar is not None
    assert bar.property("tabCount") == 1
    assert fluent_bar.property("_tabBarHeight") == 68
    assert fluent_bar.property("_tabHeight") == 52

    bar.setOpenedPaths(
        [
            "D:/Repos/PrismQML",
            "d:/repos/prismqml",
            "D:/Repos/Kaleidos",
        ]
    )
    expected_count = 3 if os.name == "nt" else 4
    assert bar.property("tabCount") == expected_count

    selected: list[str] = []
    bar.repositorySelected.connect(selected.append)
    bar._selectPath("D:/Repos/Gitora")
    assert selected == []
    bar._selectPath("D:/Repos/Kaleidos")
    assert selected == ["D:/Repos/Kaleidos"]
    fluent_bar.setProperty("currentIndex", expected_count - 1)
    bridge.object.repoOpened.emit(False, "D:/Repos/Kaleidos")
    app.processEvents()
    assert fluent_bar.property("currentIndex") == 0

    bar.setProperty("switchingEnabled", False)
    bar._closePath("D:/Repos/Gitora")
    bar._selectPath("D:/Repos/PrismQML")
    assert bar.property("tabCount") == expected_count
    assert selected == ["D:/Repos/Kaleidos"]

    bar.setProperty("switchingEnabled", True)
    selected.clear()
    bar._closePath("D:/Repos/Gitora")
    assert bar.property("tabCount") == expected_count - 1
    assert selected == ["D:/Repos/PrismQML"]
    bridge.object.repoOpened.emit(False, "D:/Repos/PrismQML")
    app.processEvents()
    assert bar.property("tabCount") == expected_count

    _destroy_repository_scene(app, engine, component, window)


def test_repository_tab_context_menu_closes_requested_ranges() -> None:
    from PySide6.QtCore import QObject, QPointF
    from PySide6.QtGui import QGuiApplication

    app, engine, component, window, bridge = _create_repository_scene()
    bar = window.findChild(QObject, "repositoryTabBar")
    fluent_bar = window.findChild(QObject, "repositoryFluentTabBar")
    context_menu = window.findChild(QObject, "repositoryTabContextMenu")
    close_action = window.findChild(QObject, "repositoryTabCloseAction")
    close_others_action = window.findChild(
        QObject, "repositoryTabCloseOthersAction"
    )
    close_right_action = window.findChild(
        QObject, "repositoryTabCloseRightAction"
    )
    assert all(
        (bar, fluent_bar, context_menu, close_action,
         close_others_action, close_right_action)
    )

    window.show()
    bar.setOpenedPaths(
        ["D:/Repos/PrismQML", "D:/Repos/Kaleidos", "D:/Repos/Mojin"]
    )
    selected: list[str] = []
    closed: list[str] = []
    bar.repositorySelected.connect(selected.append)
    bar.repositoryClosed.connect(closed.append)

    popup_windows_before = tuple(QGuiApplication.topLevelWindows())
    pointer_position = QPointF(40, 20)
    global_pointer_position = fluent_bar.mapToGlobal(
        pointer_position.x(), pointer_position.y()
    )
    fluent_bar.tabContextMenuRequested.emit(1, pointer_position)
    _pump(30)
    assert context_menu.property("isOpen")
    assert bar.property("_contextMenuPath") == "D:/Repos/PrismQML"
    popup_windows = [
        item for item in QGuiApplication.topLevelWindows()
        if item not in popup_windows_before and item.isVisible()
    ]
    assert len(popup_windows) == 1
    panel_offset = context_menu.property("_panelOffset")
    pointer_gap = context_menu.property("pointerGap")
    assert popup_windows[0].x() + panel_offset == pytest.approx(
        global_pointer_position.x() + pointer_gap
    )
    assert popup_windows[0].y() + panel_offset == pytest.approx(
        global_pointer_position.y() + pointer_gap
    )
    assert close_action.property("text") == "关闭"
    assert close_others_action.property("text") == "关闭其他标签页"
    assert close_right_action.property("text") == "关闭右侧标签页"
    assert all(
        action.property("enabled")
        for action in (close_action, close_others_action, close_right_action)
    )

    close_right_action.triggered.emit()
    _pump(30)
    assert bar.property("tabCount") == 2
    assert bar._indexForPath("D:/Repos/Gitora") == 0
    assert bar._indexForPath("D:/Repos/PrismQML") == 1
    assert bar._indexForPath("D:/Repos/Kaleidos") == -1
    assert bar._indexForPath("D:/Repos/Mojin") == -1
    assert closed == ["D:/Repos/Kaleidos", "D:/Repos/Mojin"]
    assert selected == []

    context_menu.forceReset()
    closed.clear()
    bar.setOpenedPaths(
        ["D:/Repos/PrismQML", "D:/Repos/Kaleidos", "D:/Repos/Mojin"]
    )
    fluent_bar.tabContextMenuRequested.emit(1, QPointF(40, 20))
    _pump(30)
    close_others_action.triggered.emit()
    _pump(30)
    assert bar.property("tabCount") == 1
    assert bar._indexForPath("D:/Repos/PrismQML") == 0
    assert closed == [
        "D:/Repos/Gitora", "D:/Repos/Kaleidos", "D:/Repos/Mojin"
    ]
    assert selected == ["D:/Repos/PrismQML"]
    assert not close_action.property("enabled")
    assert not close_others_action.property("enabled")
    assert not close_right_action.property("enabled")

    bridge.object._repo_path = "D:/Repos/PrismQML"
    bridge.object.repoPathChanged.emit("D:/Repos/PrismQML")
    app.processEvents()
    context_menu.forceReset()
    bar.setOpenedPaths(["D:/Repos/Gitora", "D:/Repos/Kaleidos"])
    fluent_bar.tabContextMenuRequested.emit(1, QPointF(40, 20))
    _pump(30)
    close_action.triggered.emit()
    _pump(30)
    assert bar._indexForPath("D:/Repos/Gitora") == -1
    assert bar.property("tabCount") == 2

    context_menu.forceReset()
    _destroy_repository_scene(app, engine, component, window)


def test_repository_tab_bar_keeps_prismqml_navigation_shell() -> None:
    main_source = (ROOT / "app_qml" / "qml" / "main.qml").read_text(
        encoding="utf-8"
    )
    tab_source = (COMPONENT_DIR / "RepositoryTabBar.qml").read_text(
        encoding="utf-8"
    )

    assert "Fluent.Windows" in main_source
    assert "navigationItems: root.navItems" in main_source
    assert "pageSources: root.pagePaths" in main_source
    assert "contentTopMargin: root.repositoryTabBarHeight" in main_source
    assert "RepositoryTabBar" in main_source
    assert "RepositorySearchMenu" in tab_source
    assert "signal repositorySelected(string path)" in tab_source
    assert "Fluent.TabBar" in tab_source
    assert "detailsEnabled: true" in tab_source
    assert "contextMenuEnabled: true" in tab_source
    assert "onTabContextMenuRequested" in tab_source
    assert "Fluent.ContextMenu" in tab_source
    assert 'text: "关闭其他标签页"' in tab_source
    assert 'text: "关闭右侧标签页"' in tab_source
    assert "tabBar.addButtonItem" in tab_source
