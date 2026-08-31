# coding: utf-8
"""仓库标签栏的最小 QML 加载与模型行为测试。"""
from __future__ import annotations

import os
import time
from pathlib import Path

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
    height: 120
    visible: false

    RepositoryTabBar {{
        id: bar
        objectName: \"repositoryTabBar\"
        x: 0
        y: 0
        width: 900
        height: 44
        gitBridge: bridge
        repoScanner: scanner
    }}
}}
""".encode("utf-8")


def test_repository_tab_bar_loads_and_deduplicates() -> None:
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

    from PySide6.QtCore import QObject

    bar = window.findChild(QObject, "repositoryTabBar")
    assert bar is not None
    assert bar.property("tabCount") == 1

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

    window.destroy()
    engine.deleteLater()
    app.processEvents()


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
    assert "Fluent.CloseButton" in tab_source
