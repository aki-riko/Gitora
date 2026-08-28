# coding: utf-8
"""在真实 QML 历史页验证当前分支与全部分支切换。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests.git_test_utils import build_branched_repo


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_ENV = "GITORA_HISTORY_SCOPE_SCREENSHOT"
PROBE_MARKER = "[HISTORY_SCOPE_QML_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "views"

Window {
    id: root
    width: 1100
    height: 720
    visible: true
    color: Fluent.Enums.backgroundColor

    readonly property int probeCommitCount: historyView.allCommits.length
    readonly property bool probeLoading: historyView.loading
    readonly property bool probeIncludeAllRefs: historyView.includeAllRefs
    readonly property string probeCurrentBranch: historyView.currentBranch

    function showAllRefs() {
        historyView.setHistoryScope(1)
    }

    Item {
        id: pageHost
        objectName: "historyScopePageHost"
        anchors.fill: parent

        HistoryView {
            id: historyView
            objectName: "historyScopeView"
            anchors.fill: parent
        }
    }
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


def test_history_scope_switch_renders_and_reloads_real_graph() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-history-scope-") as temp_dir:
        repo, _hashes = build_branched_repo(Path(temp_dir))
        configured = os.environ.get(SCREENSHOT_ENV, "").strip()
        output = (
            Path(configured)
            if configured
            else Path(temp_dir) / "history-scope.png"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_history_scope_qml",
                "--render-probe",
                str(repo),
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
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert PROBE_MARKER in result.stdout, diagnostic
        assert "current=4 all=5 combo=1" in result.stdout, diagnostic
        assert output.is_file() and output.stat().st_size > 10_000, diagnostic


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _pump(20)
        if predicate():
            return True
    return bool(predicate())


def _create_scene(engine):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(
        str(ROOT / "app_qml" / "qml" / "HistoryScopeProbe.qml")
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


def _render_probe(repo: Path, output: Path) -> int:
    from PySide6.QtCore import QObject, QMetaObject, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    if not bridge._svc.set_repo_path(str(repo), emit_status=False):
        raise AssertionError(f"cannot open repository: {repo}")
    engine.rootContext().setContextProperty("GitBridge", bridge)

    component, root = _create_scene(engine)
    if not _wait_until(
        lambda: not root.property("probeLoading")
        and root.property("probeCommitCount") == 4
    ):
        raise AssertionError(
            {
                "phase": "current",
                "loading": root.property("probeLoading"),
                "count": root.property("probeCommitCount"),
            }
        )
    current_count = int(root.property("probeCommitCount"))
    combo = root.findChild(QObject, "historyScopeCombo")
    current_scope_text = (
        str(combo.property("currentText")) if combo is not None else ""
    )
    if current_scope_text != "当前分支":
        raise AssertionError({"current_scope_text": current_scope_text})

    invoked = QMetaObject.invokeMethod(
        root, "showAllRefs", Qt.ConnectionType.DirectConnection
    )
    if not invoked:
        raise AssertionError("cannot invoke history scope switch")
    if not _wait_until(
        lambda: not root.property("probeLoading")
        and root.property("probeIncludeAllRefs")
        and root.property("probeCommitCount") == 5
    ):
        raise AssertionError(
            {
                "phase": "all",
                "loading": root.property("probeLoading"),
                "count": root.property("probeCommitCount"),
                "include_all_refs": root.property("probeIncludeAllRefs"),
            }
        )

    combo_index = int(combo.property("currentIndex")) if combo is not None else -1
    split = root.findChild(QObject, "historySplitPane")
    first_pane = split.findChild(QObject, "firstPane") if split else None
    second_pane = split.findChild(QObject, "secondPane") if split else None
    timeline_surface = root.findChild(QObject, "historyTimelineSurface")
    if not all((split, first_pane, second_pane, timeline_surface)):
        raise AssertionError("missing history split pane geometry probes")
    first_right = float(first_pane.property("x")) + float(
        first_pane.property("width")
    )
    surface_right = float(timeline_surface.property("x")) + float(
        timeline_surface.property("width")
    )
    second_x = float(second_pane.property("x"))
    if surface_right > first_right + 0.5 or second_x < first_right - 0.5:
        raise AssertionError(
            {
                "first_right": first_right,
                "surface_right": surface_right,
                "second_x": second_x,
            }
        )
    image = root.grabWindow()
    if combo_index != 1 or image.isNull() or not image.save(str(output), "PNG"):
        raise AssertionError(
            {"combo_index": combo_index, "image_null": image.isNull()}
        )

    print(
        f"{PROBE_MARKER} current={current_count} "
        f"all={int(root.property('probeCommitCount'))} combo={combo_index} "
        f"output={output}"
    )
    root.close()
    root.deleteLater()
    component.deleteLater()
    bridge.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--render-probe":
        raise SystemExit(
            "usage: test_history_scope_qml.py --render-probe REPO OUTPUT"
        )
    raise SystemExit(_render_probe(Path(sys.argv[2]), Path(sys.argv[3])))
