# coding: utf-8
"""新建分支入口与表单布局的 QML 回归测试。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[CREATE_BRANCH_DIALOG_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "components"

Window {
    id: root
    width: 760
    height: 620
    visible: true
    color: Fluent.Enums.backgroundColor

    CreateBranchDialog {
        id: dialog
        objectName: "createBranchDialog"
    }

    Component.onCompleted: Qt.callLater(function() {
        dialog.openFor("ae65ffe1", false)
    })
}
"""


def _probe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _run_probe(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.test_create_branch_dialog_qml",
            "--render-probe",
            str(output),
        ],
        cwd=str(ROOT),
        env=_probe_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def test_branch_and_history_views_expose_complete_create_flow() -> None:
    branch_source = (
        ROOT / "app_qml" / "qml" / "views" / "BranchView.qml"
    ).read_text(encoding="utf-8")
    history_source = (
        ROOT / "app_qml" / "qml" / "views" / "HistoryView.qml"
    ).read_text(encoding="utf-8")

    assert 'createBranchDialog.openFor("HEAD", true)' in branch_source
    assert "root.selectedCommit.hash, false" in history_source
    assert "GitBridge.createBranchAt(" not in branch_source
    assert "Fluent.MessageBox {\n        id: createDialog" not in branch_source


def test_create_branch_dialog_renders_fields_without_overlap() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-create-branch-qml-") as temp_dir:
        output = Path(temp_dir) / "create-branch-dialog.png"
        result = _run_probe(output)
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert PROBE_MARKER in result.stdout, diagnostic
        assert output.is_file() and output.stat().st_size > 5_000, diagnostic


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _render_probe(output: Path) -> int:
    from PySide6.QtCore import QObject, QPointF, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(
        str(ROOT / "app_qml" / "qml" / "CreateBranchDialogProbe.qml")
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
    _pump(600)

    object_names = [
        "createBranchDialogTitle",
        "createBranchNameLabel",
        "createBranchNameInput",
        "createBranchStartPointLabel",
        "createBranchStartPointInput",
        "createBranchCheckoutCheck",
    ]
    items = [root.findChild(QObject, name) for name in object_names]
    if any(item is None for item in items):
        raise AssertionError(dict(zip(object_names, items)))
    geometry = []
    for name, item in zip(object_names, items):
        point = item.mapToScene(QPointF(0, 0))
        geometry.append((name, point.y(), point.y() + item.height()))
    for previous, current in zip(geometry, geometry[1:]):
        if previous[2] > current[1]:
            raise AssertionError(f"overlap: {previous} -> {current}")

    image = root.grabWindow()
    if image.isNull() or not image.save(str(output), "PNG"):
        raise AssertionError("failed to save rendered dialog")
    print(f"{PROBE_MARKER} geometry={geometry} output={output}")
    root.close()
    root.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--render-probe":
        raise SystemExit("usage: test_create_branch_dialog_qml.py --render-probe OUTPUT")
    raise SystemExit(_render_probe(Path(sys.argv[2])))
