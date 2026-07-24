# coding: utf-8
"""分支强制删除菜单的页内弹层回归测试。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[BRANCH_FORCE_DELETE_MENU_PROBE]"
TARGET_BRANCH = "codex/cherry-pick-85d001f"


def _probe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
        }
    )
    windows_root = environment.get("WINDIR", "").strip()
    font_directory = Path(windows_root) / "Fonts"
    if os.name == "nt" and font_directory.is_dir():
        environment["QT_QPA_FONTDIR"] = str(font_directory)
    return environment


def test_branch_force_delete_uses_in_window_menu() -> None:
    source = (ROOT / "app_qml" / "qml" / "views" / "BranchView.qml").read_text(
        encoding="utf-8"
    )

    assert "Fluent.MenuCore" in source
    assert "useInWindowPopup: true" in source
    assert "menu: forceDeleteBranchMenu" in source
    assert "onMenuItemClicked" not in source


def test_branch_force_delete_opens_confirmation_without_deleting() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tests.test_branch_force_delete_menu_qml", "--probe"],
        cwd=str(ROOT),
        env=_probe_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    assert PROBE_MARKER in result.stdout, diagnostic
    assert "[WARNING]" not in result.stdout, diagnostic
    assert "[ERROR]" not in result.stdout, diagnostic
    assert result.stderr == "", diagnostic


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _create_scene(engine):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    source = b'''
import QtQuick
import QtQuick.Window
import "views" as Views

Window {
    width: 1280
    height: 800
    visible: true
    Views.BranchView {
        objectName: "branchView"
        anchors.fill: parent
    }
}
'''
    component = QQmlComponent(engine)
    component.setData(
        source,
        QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "BranchMenuProbe.qml")),
    )
    for _ in range(50):
        if component.status() != QQmlComponent.Status.Loading:
            break
        _pump(20)
    errors = [error.toString() for error in component.errors()]
    if component.status() != QQmlComponent.Status.Ready:
        raise AssertionError(errors)
    root = component.create(engine.rootContext())
    if root is None:
        raise AssertionError(errors)
    return component, root


def _visual_items(item):
    yield item
    for child in item.childItems():
        yield from _visual_items(child)


def _property(item, name):
    try:
        return item.property(name)
    except Exception:
        return None


def _probe() -> int:
    from PySide6.QtCore import (
        Property,
        QObject,
        QPointF,
        QTimer,
        Signal,
        Slot,
        Qt,
    )
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from prismqml import configure_qml_environment, register_types
    from prismqml.python.core import install_qt_message_handler

    class StringTask(QObject):
        succeeded = Signal(str)

    class ListTask(QObject):
        succeeded = Signal("QVariantList")

    branch_source = (
        ROOT / "app_qml" / "qml" / "views" / "BranchView.qml"
    ).read_text(encoding="utf-8")
    uses_async_queries = "branchTask.succeeded.connect" in branch_source

    class ProbeBridge(QObject):
        statusChanged = Signal()
        repoPathChanged = Signal(str)
        branchesReady = Signal(str, "QVariantList")

        def __init__(self, async_queries):
            super().__init__()
            self._repo_path = "probe-repository" if async_queries else ""
            self._async_queries = async_queries
            self.delete_calls = []
            self._tasks = []
            self.probe_branches = [
                {
                    "name": TARGET_BRANCH,
                    "isCurrent": False,
                    "isRemote": False,
                    "tracking": "aquila/" + TARGET_BRANCH,
                    "ahead": 0,
                    "behind": 0,
                },
                {
                    "name": "main",
                    "isCurrent": True,
                    "isRemote": False,
                    "tracking": "",
                    "ahead": 0,
                    "behind": 0,
                },
            ]

        @Property(str, notify=repoPathChanged)
        def repoPath(self):
            return self._repo_path

        def _task(self, result):
            task_type = ListTask if isinstance(result, list) else StringTask
            task = task_type(self)
            self._tasks.append(task)
            QTimer.singleShot(0, lambda: task.succeeded.emit(result))
            return task

        @Slot(result=QObject)
        def getCurrentBranch(self):
            if self._async_queries:
                return self._task("main")
            return "main"

        @Slot(result=QObject)
        def getRemoteInfo(self):
            if self._async_queries:
                return self._task([])
            return []

        @Slot()
        def requestBranches(self):
            QTimer.singleShot(
                0,
                lambda: self.branchesReady.emit(
                    self._repo_path, self.probe_branches
                ),
            )

        @Slot(str, bool, result="QVariantList")
        def deleteBranch(self, branch, force):
            self.delete_calls.append((branch, force))
            return [False, "probe must not delete"]

    configure_qml_environment()
    install_qt_message_handler()
    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = ProbeBridge(uses_async_queries)
    engine.rootContext().setContextProperty("GitBridge", bridge)
    component, root = _create_scene(engine)
    if not isinstance(root, QQuickWindow):
        raise AssertionError("probe root is not a window")
    root.requestActivate()
    _pump(250)
    if not uses_async_queries:
        bridge.branchesReady.emit(bridge.repoPath, bridge.probe_branches)
        _pump(50)

    items = list(_visual_items(root.contentItem()))
    button = next(
        item
        for item in items
        if item.objectName() == "deleteBranchButton"
        and _property(item, "branchName") == TARGET_BRANCH
    )
    menu = next(
        item
        for item in items
        if item.objectName() == "forceDeleteBranchMenu"
        and _property(item, "branchName") == TARGET_BRANCH
    )
    danger = root.findChild(QObject, "forceDeleteBranchDanger")
    if danger is None:
        raise AssertionError("force-delete confirmation dialog is missing")
    if not bool(_property(menu, "useInWindowPopup")):
        raise AssertionError("force-delete menu is not in-window")
    if bool(_property(menu, "useQtPopupWindow")):
        raise AssertionError("force-delete menu still uses a native popup")

    arrow = button.mapToScene(
        QPointF(button.width() - 12, button.height() / 2)
    ).toPoint()
    QTest.mouseClick(
        root,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        arrow,
    )
    _pump(120)
    if not bool(_property(menu, "isOpen")):
        raise AssertionError("force-delete menu did not open")

    action = next(
        item
        for item in _visual_items(root.contentItem())
        if item.objectName() == "forceDeleteBranchAction"
        and _property(item, "text") == "强制删除"
        and item.isVisible()
    )
    action_point = action.mapToScene(
        QPointF(action.width() / 2, action.height() / 2)
    ).toPoint()
    QTest.mouseClick(
        root,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        action_point,
    )
    _pump(150)

    if not bool(_property(danger, "_isOpen")):
        raise AssertionError("force-delete confirmation did not open")
    if _property(danger, "_branch") != TARGET_BRANCH:
        raise AssertionError(_property(danger, "_branch"))
    if bridge.delete_calls:
        raise AssertionError(bridge.delete_calls)

    print(f"{PROBE_MARKER} branch={TARGET_BRANCH} delete_calls=0")
    root.close()
    root.deleteLater()
    component.deleteLater()
    bridge.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--probe":
        raise SystemExit(_probe())
    raise SystemExit("usage: test_branch_force_delete_menu_qml.py --probe")
