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


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        _pump(10)
    return bool(predicate())


class _DummyGitBridge:
    def __init__(
        self, repo_path: str, tab_poll_interval: int = 10000
    ) -> None:
        from PySide6.QtCore import QObject, Property, Signal, Slot

        class Bridge(QObject):
            repoPathChanged = Signal(str)
            repoOpened = Signal(bool, str)
            repoOpenRejected = Signal(str, str)
            openedReposRestored = Signal("QVariantList", str)
            statusChanged = Signal()
            statusReady = Signal(str, int)
            branchReady = Signal(str, str)
            worktreeStateReady = Signal(str, "QVariantList")

            def __init__(self, path: str, interval: int) -> None:
                super().__init__()
                self._repo_path = path
                self._tab_poll_interval = interval
                self.saved_sessions: list[tuple[list[str], str]] = []
                self.tab_snapshot_calls: list[tuple[list[str], str]] = []

            def _get_repo_path(self) -> str:
                return self._repo_path

            def _get_tab_poll_interval(self) -> int:
                return self._tab_poll_interval

            @Slot(result="QVariantList")
            def getRecentRepos(self) -> list[str]:
                return ["D:/Repos/PrismQML", "D:/Repos/Kaleidos"]

            @Slot("QVariantList", str)
            def saveOpenedRepos(self, paths: list, active: str) -> None:
                self.saved_sessions.append(
                    ([str(item) for item in (paths or [])], str(active or ""))
                )

            @Slot()
            def requestStatus(self) -> None:
                return None

            @Slot("QVariantList", str)
            def requestTabSnapshots(self, paths: list, active: str) -> None:
                self.tab_snapshot_calls.append(
                    ([str(item) for item in (paths or [])], str(active or ""))
                )

            @Slot()
            def requestWorktreeState(self) -> None:
                return None

            repoPath = Property(str, _get_repo_path, notify=repoPathChanged)
            tabPollIntervalMs = Property(
                int, _get_tab_poll_interval, constant=True
            )

        self.object = Bridge(repo_path, tab_poll_interval)


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


def _create_repository_scene(tab_poll_interval_ms: int = 10000):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from prismqml import qml_path

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(qml_path().parent))

    bridge = _DummyGitBridge(
        "D:/Repos/Gitora", tab_poll_interval=tab_poll_interval_ms
    )
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


def test_repository_tab_bar_workspace_combo_switches_worktree() -> None:
    from PySide6.QtCore import QObject

    app, engine, component, window, bridge = _create_repository_scene()
    bar = window.findChild(QObject, "repositoryTabBar")
    combo = window.findChild(QObject, "workspaceSwitcherComboBox")
    assert bar is not None
    assert combo is not None
    window.show()
    _pump(30)

    bridge.object.worktreeStateReady.emit(
        "D:/Repos/Gitora",
        [
            {"path": "D:/Repos/Gitora", "branch": "master"},
            {"path": "D:/Repos/Gitora-feature", "branch": "feature/ui"},
            {"path": "D:/Repos/Gitora-stale", "prunable": True},
        ],
    )
    app.processEvents()
    assert combo.property("style") == 2
    assert combo.property("visible")
    model = combo.property("model")
    if hasattr(model, "toVariant"):
        model = model.toVariant()
    assert [item["text"] for item in model] == ["Gitora", "Gitora-feature"]
    assert combo.property("currentIndex") == 0

    selected: list[str] = []
    bar.repositorySelected.connect(selected.append)
    combo.activated.emit(1)
    assert selected == ["D:/Repos/Gitora-feature"]

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
    assert _wait_until(lambda: bool(context_menu.property("isOpen")))
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
    assert _wait_until(lambda: bool(context_menu.property("isOpen")))
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
    assert _wait_until(lambda: bool(context_menu.property("isOpen")))
    close_action.triggered.emit()
    _pump(30)
    assert bar._indexForPath("D:/Repos/Gitora") == -1
    assert bar.property("tabCount") == 2

    context_menu.forceReset()
    _destroy_repository_scene(app, engine, component, window)


def test_repository_entry_actions_are_merged_into_tab_add_button() -> None:
    """仓库入口(打开/初始化)统一收敛到标签栏“+”菜单,仓库页页头不再重复提供。"""
    tab_source = (COMPONENT_DIR / "RepositoryTabBar.qml").read_text(
        encoding="utf-8"
    )
    repo_source = (
        ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
    ).read_text(encoding="utf-8")

    # “+”单击打开入口菜单,而不是直接打开仓库检索列表。
    assert "onTabAddClicked: root._openRepositoryEntryMenu()" in tab_source
    assert "repositoryEntryMenu.show(tabBar.addButtonItem)" in tab_source
    assert 'text: "打开仓库…"' in tab_source
    assert 'text: "最近仓库…"' in tab_source
    assert 'text: "初始化仓库…"' in tab_source
    assert "onTriggered: root._openRepositoryFolder()" in tab_source
    assert "onTriggered: root._openRepositoryPicker()" in tab_source
    assert "onTriggered: root._startRepositoryInit()" in tab_source

    # 打开:目录选择 + 最近仓库检索;初始化:选目录后调后端并进入惰性创建的引导窗口。
    assert "id: openFolderDialog" in tab_source
    assert "id: initFolderDialog" in tab_source
    assert "root.gitBridge.initRepo(path)" in tab_source
    assert "function _ensureInitGuide()" in tab_source
    assert "id: initGuideLoader" in tab_source
    assert "active: false" in tab_source

    # 仓库页页头不再保留这两个入口,也不残留其对话框/引导实现。
    assert 'objectName: "repositoryOpenButton"' not in repo_source
    assert 'text: "初始化"' not in repo_source
    assert "initFolderDialog" not in repo_source
    assert "initGuideLoader" not in repo_source
    assert "repositorySearchMenu" not in repo_source


def test_repository_entry_menu_opens_from_add_button() -> None:
    from PySide6.QtCore import QObject

    app, engine, component, window, bridge = _create_repository_scene()
    bar = window.findChild(QObject, "repositoryTabBar")
    fluent_bar = window.findChild(QObject, "repositoryFluentTabBar")
    entry_menu = window.findChild(QObject, "repositoryEntryMenu")
    open_action = window.findChild(QObject, "repositoryEntryOpenAction")
    recent_action = window.findChild(QObject, "repositoryEntryRecentAction")
    init_action = window.findChild(QObject, "repositoryEntryInitAction")
    search_menu = window.findChild(QObject, "repositorySearchMenu")
    assert all(
        (bar, fluent_bar, entry_menu, open_action, recent_action,
         init_action, search_menu)
    )
    assert [
        open_action.property("text"),
        recent_action.property("text"),
        init_action.property("text"),
    ] == ["打开仓库…", "最近仓库…", "初始化仓库…"]

    window.show()
    assert not entry_menu.property("isOpen")
    fluent_bar.tabAddClicked.emit()
    assert _wait_until(lambda: bool(entry_menu.property("isOpen")))
    assert not search_menu.property("isOpen")

    # “最近仓库…”仍走原来的检索列表(带路径省略显示)。
    entry_menu.forceReset()
    recent_action.triggered.emit()
    assert _wait_until(lambda: bool(search_menu.property("isOpen")))

    search_menu.forceReset()
    entry_menu.forceReset()

    # 初始化引导窗口保持惰性,但必须能在标签栏内真实实例化。
    guide = bar._ensureInitGuide()
    _pump(30)
    assert guide is not None
    assert guide.property("repoPath") == ""
    step_titles = guide.property("stepTitles")
    if hasattr(step_titles, "toVariant"):
        step_titles = step_titles.toVariant()
    assert [str(title) for title in step_titles] == [
        "欢迎", "用户信息", "远程仓库", "完成"
    ]

    _destroy_repository_scene(app, engine, component, window)


def _tab_paths(bar) -> list[str]:
    """读取标签栏当前可见顺序的仓库路径。"""
    tabs = bar.property("_tabs")
    if hasattr(tabs, "toVariant"):
        tabs = tabs.toVariant()
    return [str(tab["path"]) for tab in (tabs or [])]


def test_repository_tab_bar_restores_and_persists_session() -> None:
    from PySide6.QtCore import QObject

    app, engine, component, window, bridge = _create_repository_scene()
    bar = window.findChild(QObject, "repositoryTabBar")
    assert bar is not None

    # 恢复完成前不允许回写，避免用启动中的空标签覆盖上次会话快照。
    assert not bar.property("_sessionRestored")
    bar._persistSession()
    assert bridge.object.saved_sessions == []

    session_paths = [
        "D:/Repos/PrismQML",
        "d:/repos/prismqml",
        "D:/Repos/Kaleidos",
        "D:/Repos/Mojin",
    ]
    bridge.object.openedReposRestored.emit(session_paths, "D:/Repos/Kaleidos")
    app.processEvents()

    expected_count = 3 if os.name == "nt" else 4
    assert bar.property("tabCount") == expected_count
    assert bar.property("_sessionRestored")
    assert bar._indexForPath("D:/Repos/PrismQML") == 0
    assert bar._indexForPath("D:/Repos/Kaleidos") == expected_count - 2
    assert bar._indexForPath("D:/Repos/Mojin") == expected_count - 1
    # 恢复出的标签不包含未在快照里的当前 repoPath。
    assert bar._indexForPath("D:/Repos/Gitora") == -1
    assert bridge.object.saved_sessions == []

    # 关闭标签页后立刻落盘，快照里不再有被关掉的仓库。
    bar._closePath("D:/Repos/Mojin")
    app.processEvents()
    assert bridge.object.saved_sessions
    persisted_paths, _persisted_active = bridge.object.saved_sessions[-1]
    assert "D:/Repos/Mojin" not in persisted_paths
    assert len(persisted_paths) == expected_count - 1

    # 打开新仓库后同样落盘，且带上当前活动仓库。
    bridge.object.saved_sessions.clear()
    bridge.object._repo_path = "D:/Repos/Gitora"
    bridge.object.repoPathChanged.emit("D:/Repos/Gitora")
    app.processEvents()
    assert bridge.object.saved_sessions
    persisted_paths, persisted_active = bridge.object.saved_sessions[-1]
    assert "D:/Repos/Gitora" in persisted_paths
    assert persisted_active == "D:/Repos/Gitora"

    # 关闭“当前活动标签”：activePath 绑定 gitBridge.repoPath，要等异步打开完成
    # 才更新，落盘时它还指向正被关闭的仓库。此刻必须写入接管的那个仓库，
    # 否则 active 不在列表里，重启会回退到第一个标签。
    bridge.object.saved_sessions.clear()
    tabs_before_close = _tab_paths(bar)
    active_index = tabs_before_close.index("D:/Repos/Gitora")
    expected_fallback = (
        tabs_before_close[active_index + 1]
        if active_index < len(tabs_before_close) - 1
        else tabs_before_close[active_index - 1]
    )
    bar._closePath("D:/Repos/Gitora")
    app.processEvents()
    assert bridge.object.saved_sessions
    persisted_paths, persisted_active = bridge.object.saved_sessions[-1]
    assert "D:/Repos/Gitora" not in persisted_paths
    assert persisted_active == expected_fallback
    # active 必须是列表成员，否则存储层只能回退到第一项。
    assert persisted_active in persisted_paths

    # 恢复现场：把 Gitora 重新作为活动仓库放回标签栏，供后续重排断言使用。
    bridge.object._repo_path = "D:/Repos/Gitora"
    bridge.object.repoPathChanged.emit("D:/Repos/Gitora")
    app.processEvents()

    # 拖动重排必须持久化“新顺序”，而不是只触发一次写盘。
    bridge.object.saved_sessions.clear()
    order_before = _tab_paths(bar)
    bar._reorderTabs(0, 1)
    app.processEvents()
    assert bridge.object.saved_sessions
    persisted_paths, _persisted_active = bridge.object.saved_sessions[-1]
    expected_order = order_before[:]
    expected_order.insert(1, expected_order.pop(0))
    assert persisted_paths == expected_order
    assert persisted_paths != order_before
    # 落盘顺序必须与标签栏当前可见顺序一致。
    assert persisted_paths == _tab_paths(bar)

    # 真实拖拽路径：引擎 TabBar 释放拖拽时发 tabsReordered，
    # 必须走到同一条持久化分支（而不是只有直接调 _reorderTabs 才生效）。
    fluent_bar = window.findChild(QObject, "repositoryFluentTabBar")
    assert fluent_bar is not None
    assert fluent_bar.property("movable")
    bridge.object.saved_sessions.clear()
    order_before = _tab_paths(bar)
    last_index = len(order_before) - 1
    fluent_bar.tabsReordered.emit(last_index, 0)
    app.processEvents()
    assert bridge.object.saved_sessions
    persisted_paths, _persisted_active = bridge.object.saved_sessions[-1]
    expected_order = order_before[:]
    expected_order.insert(0, expected_order.pop(last_index))
    assert persisted_paths == expected_order
    assert persisted_paths == _tab_paths(bar)

    _destroy_repository_scene(app, engine, component, window)


def _tab_subtitles(bar) -> list[str]:
    """读取标签栏当前每个标签的副标题(分支文本)。"""
    tabs = bar.property("_tabs")
    if hasattr(tabs, "toVariant"):
        tabs = tabs.toVariant()
    return [str(tab.get("subtitle", "")) for tab in (tabs or [])]


def test_repository_tab_bar_applies_background_branch_updates() -> None:
    """启动恢复出的非活动标签页，收到后台分支结果后必须直接显示分支。"""
    from PySide6.QtCore import QObject

    app, engine, component, window, bridge = _create_repository_scene()
    bar = window.findChild(QObject, "repositoryTabBar")
    assert bar is not None

    bridge.object.openedReposRestored.emit(
        ["D:/Repos/PrismQML", "D:/Repos/Kaleidos"], "D:/Repos/PrismQML"
    )
    app.processEvents()
    assert bar.property("tabCount") == 2
    # 活动标签由后端异步打开，其余标签在后台分支补齐前保持未读取。
    assert _tab_subtitles(bar) == ["打开中…", "未读取分支"]

    # 后台补齐：非活动标签的分支结果同样要落到对应标签上。
    bridge.object.branchReady.emit("D:/Repos/Kaleidos", "master")
    app.processEvents()
    assert _tab_subtitles(bar) == ["打开中…", "master"]
    assert bar.property("_tabs").toVariant()[1]["branch"] == "master"

    # 迟到的结果不能让已关闭的标签重新出现。
    bar._closePath("D:/Repos/Kaleidos")
    app.processEvents()
    bridge.object.branchReady.emit("D:/Repos/Kaleidos", "master")
    bridge.object.branchReady.emit("D:/Repos/Mojin", "dev")
    app.processEvents()
    assert bar.property("tabCount") == 1
    assert bar._indexForPath("D:/Repos/Kaleidos") == -1
    assert bar._indexForPath("D:/Repos/Mojin") == -1

    _destroy_repository_scene(app, engine, component, window)


def test_repository_tab_bar_polls_tab_snapshots_periodically() -> None:
    """打开的页面要定时轮询：restore 后立即拉一轮，徽标随轮询结果更新，
    迟到的快照不能复活已关闭的标签。"""
    from PySide6.QtCore import QObject

    # 轮询测试专用短周期；其余测试用默认大周期，避免高频 Timer 干扰 Popup。
    app, engine, component, window, bridge = _create_repository_scene(
        tab_poll_interval_ms=30
    )
    bar = window.findChild(QObject, "repositoryTabBar")
    assert bar is not None

    bridge.object.openedReposRestored.emit(
        ["D:/Repos/PrismQML", "D:/Repos/Kaleidos"], "D:/Repos/PrismQML"
    )
    app.processEvents()
    # 会话恢复后立即触发一轮快照轮询（Qt.callLater），全部标签路径原样上报，
    # 活动仓库由后端剔除，不重复回传。
    assert bridge.object.tab_snapshot_calls, "restore 后必须立即拉一轮标签快照"
    polled_paths, polled_active = bridge.object.tab_snapshot_calls[-1]
    assert polled_paths == ["D:/Repos/PrismQML", "D:/Repos/Kaleidos"]
    # restore 阶段活动仓库还没完成异步打开，activePath 仍是当前 repoPath。
    assert polled_active == "D:/Repos/Gitora"

    # 定时器按 tabPollIntervalMs(dummy=30ms) 周期继续触发。
    calls_after_restore = len(bridge.object.tab_snapshot_calls)
    _pump(200)
    assert len(bridge.object.tab_snapshot_calls) > calls_after_restore

    # 轮询结果落到对应标签：变更数与“干净”徽标随结果刷新。
    bridge.object.statusReady.emit("D:/Repos/Kaleidos", 26)
    app.processEvents()
    tabs = bar.property("_tabs").toVariant()
    assert tabs[1]["badgeText"] == "26"
    bridge.object.statusReady.emit("D:/Repos/Kaleidos", 0)
    app.processEvents()
    tabs = bar.property("_tabs").toVariant()
    assert tabs[1]["badgeText"] == "干净"

    # 迟到的快照不能让已关闭的标签重新出现。
    bar._closePath("D:/Repos/Kaleidos")
    app.processEvents()
    bridge.object.statusReady.emit("D:/Repos/Kaleidos", 5)
    bridge.object.branchReady.emit("D:/Repos/Kaleidos", "master")
    app.processEvents()
    assert bar.property("tabCount") == 1
    assert bar._indexForPath("D:/Repos/Kaleidos") == -1

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
