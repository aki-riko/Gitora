# coding: utf-8
"""远程分支检出弹窗的离屏布局回归测试。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[REMOTE_CHECKOUT_DIALOG_PROBE]"
REMOTE_BRANCH = "codex/cherry-pick-85d001f"
LOCAL_BRANCH = "codex/cherry-pick-85d001f"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "views"

Window {
    width: 900
    height: 700
    visible: true
    color: Fluent.Enums.backgroundColor

    BranchView {
        objectName: "branchView"
        anchors.fill: parent
    }
}
"""


def _probe_environment(config_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
            "LOCALAPPDATA": str(config_root),
            "XDG_CONFIG_HOME": str(config_root),
        }
    )
    windows_root = environment.get("WINDIR", "").strip()
    font_directory = Path(windows_root) / "Fonts"
    if os.name == "nt" and font_directory.is_dir():
        environment["QT_QPA_FONTDIR"] = str(font_directory)
    return environment


def test_remote_checkout_dialog_has_no_overlapping_rows() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-remote-checkout-qml-") as temp_dir:
        temp_root = Path(temp_dir)
        output = temp_root / "remote-checkout-dialog.png"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_remote_branch_checkout_dialog_qml",
                "--render-probe",
                str(output),
            ],
            cwd=str(ROOT),
            env=_probe_environment(temp_root / "config"),
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
        assert output.is_file() and output.stat().st_size > 5_000, diagnostic


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _create_scene(engine):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(
        str(ROOT / "app_qml" / "qml" / "RemoteCheckoutDialogProbe.qml")
    )
    component.setData(PROBE_SOURCE, base_url)
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


def _item_geometry(item) -> tuple[float, float]:
    from PySide6.QtCore import QPointF

    point = item.mapToScene(QPointF(0, 0))
    return point.y(), point.y() + item.height()


def _render_probe(output: Path) -> int:
    from PySide6.QtCore import QObject, QMetaObject, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import configure_qml_environment, register_types
    from prismqml.python.core import install_qt_message_handler

    from app_qml.backend.git_bridge import GitBridge

    configure_qml_environment()
    install_qt_message_handler()
    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    engine.rootContext().setContextProperty("GitBridge", bridge)
    component, root = _create_scene(engine)
    _pump(100)

    branch_view = root.findChild(QObject, "branchView")
    dialog = root.findChild(QObject, "remoteCheckoutDialog")
    target_label = root.findChild(QObject, "remoteCheckoutTargetLabel")
    local_input = root.findChild(QObject, "remoteCheckoutLocalInput")
    if any(item is None for item in (branch_view, dialog, target_label, local_input)):
        raise AssertionError("missing remote-checkout dialog item")
    branch_view.setProperty("_remoteCheckoutTarget", REMOTE_BRANCH)
    local_input.setProperty("text", LOCAL_BRANCH)
    if not QMetaObject.invokeMethod(dialog, "open", Qt.ConnectionType.DirectConnection):
        raise AssertionError("failed to open remote-checkout dialog")
    _pump(600)

    title = next(
        (
            item
            for item in dialog.findChildren(QObject)
            if item.property("text") == "获取并检出远程分支"
        ),
        None,
    )
    if title is None:
        raise AssertionError("missing visible remote-checkout title")
    geometry = {
        "title": _item_geometry(title),
        "target": _item_geometry(target_label),
        "input": _item_geometry(local_input),
    }
    for previous, current in (("title", "target"), ("target", "input")):
        if geometry[previous][1] > geometry[current][0] + 0.25:
            raise AssertionError(
                f"overlap: {previous}={geometry[previous]} -> "
                f"{current}={geometry[current]}"
            )

    image = root.grabWindow()
    if image.isNull() or not image.save(str(output), "PNG"):
        raise AssertionError("failed to save rendered dialog")
    print(f"{PROBE_MARKER} geometry={geometry} output={output}")
    root.close()
    root.deleteLater()
    component.deleteLater()
    bridge.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--render-probe":
        raise SystemExit(_render_probe(Path(sys.argv[2])))
    raise SystemExit(
        "usage: test_remote_branch_checkout_dialog_qml.py --render-probe OUTPUT"
    )
