# coding: utf-8
"""新建分支入口与表单布局的 QML 回归测试。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[CREATE_BRANCH_DIALOG_PROBE]"
OPERATION_PROBE_MARKER = "[CREATE_BRANCH_OPERATION_PROBE]"
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
OPERATION_PROBE_SOURCE = b"""
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
        dialog.openFor(OperationStartPoint, false)
    })
}
"""

DIALOG_ITEM_NAMES = [
    "createBranchDialogTitle",
    "createBranchNameLabel",
    "createBranchNameInput",
    "createBranchStartPointLabel",
    "createBranchStartPointInput",
    "createBranchBehaviorHint",
    "createBranchCheckoutCheck",
]


def _probe_environment(config_root: Path | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
        }
    )
    if config_root is not None:
        environment["LOCALAPPDATA"] = str(config_root)
        environment["XDG_CONFIG_HOME"] = str(config_root)
    windows_root = environment.get("WINDIR", "").strip()
    font_directory = Path(windows_root) / "Fonts"
    if os.name == "nt" and font_directory.is_dir():
        environment["QT_QPA_FONTDIR"] = str(font_directory)
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


def _run_operation_probe(
    repo: Path, start_point: str, config_root: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.test_create_branch_dialog_qml",
            "--operation-probe",
            str(repo),
            start_point,
        ],
        cwd=str(ROOT),
        env=_probe_environment(config_root),
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


def test_create_branch_dialog_uses_specific_error_title() -> None:
    dialog_source = (
        ROOT / "app_qml" / "qml" / "components" / "CreateBranchDialog.qml"
    ).read_text(encoding="utf-8")

    assert 'desktop.error("无法创建分支", result[1]' in dialog_source


def test_create_branch_dialog_renders_fields_without_overlap() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-create-branch-qml-") as temp_dir:
        output = Path(temp_dir) / "create-branch-dialog.png"
        result = _run_probe(output)
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert PROBE_MARKER in result.stdout, diagnostic
        assert output.is_file() and output.stat().st_size > 5_000, diagnostic


def test_dialog_creates_from_selected_commit_without_switching() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-create-branch-flow-") as temp_dir:
        temp_root = Path(temp_dir)
        repo = init_repo(temp_root / "repo")
        config_root = temp_root / "config"
        write_file(repo, "tracked.txt", "base\n")
        base_commit = commit_all(repo, "base")
        write_file(repo, "tracked.txt", "latest\n")
        commit_all(repo, "latest")
        write_file(repo, "tracked.txt", "uncommitted\n")
        before_diff = run_git(repo, "diff").stdout

        result = _run_operation_probe(repo, base_commit, config_root)

        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert OPERATION_PROBE_MARKER in result.stdout, diagnostic
        assert "[WARNING]" not in result.stdout, diagnostic
        assert "[ERROR]" not in result.stdout, diagnostic
        assert result.stderr == "", diagnostic
        cached_repos = json.loads(
            (config_root / "Gitora" / "recent_repos.json").read_text(
                encoding="utf-8"
            )
        )["repos"]
        assert cached_repos == [str(repo)]
        assert (
            run_git(repo, "rev-parse", "refs/heads/qml-from-base").stdout.strip()
            == base_commit
        )
        assert (
            run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            == "master"
        )
        assert run_git(repo, "diff").stdout == before_diff


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _create_scene(engine, source: bytes):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(
        str(ROOT / "app_qml" / "qml" / "CreateBranchDialogProbe.qml")
    )
    component.setData(source, base_url)
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


def _dialog_geometry(root):
    from PySide6.QtCore import QObject, QPointF

    items = [root.findChild(QObject, name) for name in DIALOG_ITEM_NAMES]
    if any(item is None for item in items):
        raise AssertionError(dict(zip(DIALOG_ITEM_NAMES, items)))
    geometry = []
    for name, item in zip(DIALOG_ITEM_NAMES, items):
        point = item.mapToScene(QPointF(0, 0))
        geometry.append((name, point.y(), point.y() + item.height()))
    for previous, current in zip(geometry, geometry[1:]):
        if previous[2] > current[1] + 0.25:
            raise AssertionError(f"overlap: {previous} -> {current}")
    return geometry


def _render_probe(output: Path) -> int:
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import configure_qml_environment, register_types
    from prismqml.python.core import install_qt_message_handler

    configure_qml_environment()
    install_qt_message_handler()
    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    component, root = _create_scene(engine, PROBE_SOURCE)
    frames = []
    elapsed = 0
    for delta in (1, 39, 60, 100, 200):
        _pump(delta)
        elapsed += delta
        frames.append((elapsed, _dialog_geometry(root)))

    image = root.grabWindow()
    if image.isNull() or not image.save(str(output), "PNG"):
        raise AssertionError("failed to save rendered dialog")
    print(f"{PROBE_MARKER} frames={frames} output={output}")
    root.close()
    root.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


def _operation_probe(repo: Path, start_point: str) -> int:
    from PySide6.QtCore import QObject, QMetaObject, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import configure_qml_environment, register_types
    from prismqml.python.core import global_task_pool, install_qt_message_handler

    from app_qml.backend.git_bridge import GitBridge

    configure_qml_environment()
    install_qt_message_handler()
    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    if not bridge.setRepoPath(str(repo)):
        raise AssertionError(f"failed to open repo: {repo}")
    engine.rootContext().setContextProperty("GitBridge", bridge)
    engine.rootContext().setContextProperty("OperationStartPoint", start_point)
    component, root = _create_scene(engine, OPERATION_PROBE_SOURCE)
    _pump(100)

    dialog = root.findChild(QObject, "createBranchDialog")
    branch_input = root.findChild(QObject, "createBranchNameInput")
    start_input = root.findChild(QObject, "createBranchStartPointInput")
    checkout = root.findChild(QObject, "createBranchCheckoutCheck")
    if any(item is None for item in (dialog, branch_input, start_input, checkout)):
        raise AssertionError("missing create-branch form item")
    if start_input.property("text") != start_point:
        raise AssertionError("selected commit was not prefilled")
    if bool(checkout.property("checked")):
        raise AssertionError("history flow unexpectedly enables checkout")
    branch_input.setProperty("text", "qml-from-base")
    if not QMetaObject.invokeMethod(
        dialog, "accept", Qt.ConnectionType.DirectConnection
    ):
        raise AssertionError("failed to submit create-branch dialog")
    if not global_task_pool().waitForDone(5000):
        raise AssertionError("create-branch task did not finish before timeout")
    app.processEvents()
    app.processEvents()

    print(
        f"{OPERATION_PROBE_MARKER} start={start_point} "
        f"checkout={checkout.property('checked')}"
    )
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
    if len(sys.argv) == 4 and sys.argv[1] == "--operation-probe":
        raise SystemExit(_operation_probe(Path(sys.argv[2]), sys.argv[3]))
    raise SystemExit(
        "usage: test_create_branch_dialog_qml.py "
        "--render-probe OUTPUT | --operation-probe REPO START_POINT"
    )
