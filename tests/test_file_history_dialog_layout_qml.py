# coding: utf-8
"""文件历史弹窗标题与双栏布局的离屏几何回归测试。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[FILE_HISTORY_DIALOG_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "components"

Window {
    width: 1000
    height: 760
    visible: true
    color: Fluent.Enums.backgroundColor

    FileHistoryDialog {
        id: dialog
        objectName: "fileHistoryDialog"
    }

    Component.onCompleted: Qt.callLater(function() { dialog.open() })
}
"""


def _probe_environment(config_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_QPA_FONTDIR": str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"),
            "PYTHONUTF8": "1",
            "LOCALAPPDATA": str(config_root),
            "XDG_CONFIG_HOME": str(config_root),
        }
    )
    return environment


def test_file_history_dialog_keeps_panes_side_by_side() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-file-history-qml-") as temp_dir:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_file_history_dialog_layout_qml",
                "--layout-probe",
            ],
            cwd=str(ROOT),
            env=_probe_environment(Path(temp_dir)),
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


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _geometry(item) -> tuple[float, float, float, float]:
    from PySide6.QtCore import QPointF

    point = item.mapToScene(QPointF(0, 0))
    return point.x(), point.y(), point.x() + item.width(), point.y() + item.height()


def _layout_probe() -> int:
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    engine.rootContext().setContextProperty("GitBridge", bridge)
    component = QQmlComponent(engine)
    component.setData(
        PROBE_SOURCE,
        QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "FileHistoryProbe.qml")),
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
    _pump(600)

    title = root.findChild(QObject, "fileHistoryDialogTitle")
    left = root.findChild(QObject, "fileHistoryListPane")
    right = root.findChild(QObject, "fileHistoryContentPane")
    if any(item is None for item in (title, left, right)):
        raise AssertionError("missing file-history layout item")
    geometry = {
        "title": _geometry(title),
        "left": _geometry(left),
        "right": _geometry(right),
    }
    if geometry["title"][3] > min(geometry["left"][1], geometry["right"][1]) + 0.25:
        raise AssertionError(f"title overlap: {geometry}")
    if abs(geometry["left"][1] - geometry["right"][1]) > 0.25:
        raise AssertionError(f"panes are not on the same row: {geometry}")
    if geometry["left"][2] > geometry["right"][0] + 0.25:
        raise AssertionError(f"pane overlap: {geometry}")

    print(f"{PROBE_MARKER} geometry={geometry}")
    root.close()
    root.deleteLater()
    component.deleteLater()
    bridge.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--layout-probe":
        raise SystemExit(_layout_probe())
    raise SystemExit("usage: test_file_history_dialog_layout_qml.py --layout-probe")
