"""提交文件列表应完整接收数据，但只创建视口附近的 delegate。"""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtWidgets import QApplication

from app.common.git_service import FileChange, FileStatus


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[COMMIT_FILES_VIRTUALIZATION_QML_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "components"

Window {
    width: 900
    height: 620
    visible: true
    color: Fluent.Enums.backgroundColor

    CommitFilesPanel {
        id: panel
        objectName: "commitFilesPanel"
        anchors.fill: parent
        commit: { "hash": "abc123" }
    }
}
"""


def _pump(app: QApplication, milliseconds: int = 20) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    app.processEvents()


def _visual_items(item: QObject):
    yield item
    children = item.childItems() if hasattr(item, "childItems") else item.children()
    for child in children:
        yield from _visual_items(child)


def test_commit_file_panel_virtualizes_all_returned_rows() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_QUICK_BACKEND"] = "software"
    app = QApplication.instance() or QApplication([])

    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge

    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    bridge._svc._repo_path = "repo"
    rows = [
        FileChange(f"file-{index:04d}.txt", FileStatus.ADDED, False)
        for index in range(4142)
    ]
    bridge._svc.get_commit_files_preview = lambda _hash: (  # type: ignore[method-assign]
        rows,
        len(rows),
        False,
        {"A": len(rows)},
    )
    engine.rootContext().setContextProperty("GitBridge", bridge)

    component = QQmlComponent(engine)
    component.setData(
        PROBE_SOURCE,
        QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "CommitFilesVirtualProbe.qml")),
    )
    while component.isLoading():
        _pump(app)
    if component.status() != QQmlComponent.Status.Ready:
        raise AssertionError([error.toString() for error in component.errors()])
    root = component.create()
    if root is None:
        raise AssertionError([error.toString() for error in component.errors()])

    try:
        panel = root.findChild(QObject, "commitFilesPanel")
        if panel is None:
            raise AssertionError("missing commit files panel")
        for _ in range(100):
            if not bool(panel.property("loading")):
                break
            _pump(app)
        list_view = root.findChild(QObject, "historyCommitFilesList")
        if list_view is None:
            raise AssertionError("missing commit files list")
        assert list_view.property("selectable") is False
        internal_list = list_view.property("flickableItem")
        assert internal_list is not None
        assert internal_list.property("highlight") is None
        delegate_count = sum(
            1
            for item in _visual_items(root)
            if item.objectName() == "historyCommitFileRow"
        )
        print(
            f"{PROBE_MARKER} rows={panel.property('fileRows').__len__()} "
            f"delegates={delegate_count} count={list_view.property('count')}"
        )
        assert panel.property("fileRows").__len__() == 4142
        assert list_view.property("count") == 4142
        assert delegate_count < 100
    finally:
        root.deleteLater()
        bridge.deleteLater()
        engine.deleteLater()
        app.processEvents()
