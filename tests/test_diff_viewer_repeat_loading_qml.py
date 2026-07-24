# coding: utf-8
"""验证 DiffViewer 连续接收相同 diff 时能结束第二轮加载。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[DIFF_REPEAT_PROBE]"
REPEATED_DIFF = """diff --git a/sounds/sound_definitions.json b/sounds/sound_definitions.json
index 1111111..2222222 100644
--- a/sounds/sound_definitions.json
+++ b/sounds/sound_definitions.json
@@ -1 +1 @@
-{"volume": 1}
+{"volume": 0.8}
"""
PROBE_SOURCE = b"""
import QtQuick
import "components"

Item {
    property bool firstStillLoading: true
    property bool secondStillLoading: true

    DiffViewer { id: viewer }

    Component.onCompleted: {
        viewer.setLoading("loading-1")
        viewer.setDiff(RepeatedDiff, "")
        firstStillLoading = viewer.loading

        viewer.setLoading("loading-2")
        viewer.setDiff(RepeatedDiff, "")
        secondStillLoading = viewer.loading
    }
}
"""


def test_repeated_diff_finishes_both_loading_cycles() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "tests.test_diff_viewer_repeat_loading_qml", "--probe"],
        cwd=str(ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    assert f"{PROBE_MARKER} first=false second=false" in result.stdout, diagnostic


def _run_probe() -> int:
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    engine.rootContext().setContextProperty("GitBridge", bridge)
    engine.rootContext().setContextProperty("RepeatedDiff", REPEATED_DIFF)

    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "DiffRepeatProbe.qml"))
    component.setData(PROBE_SOURCE, base_url)
    errors = [error.toString() for error in component.errors()]
    assert component.status() == QQmlComponent.Status.Ready, errors
    root = component.create(engine.rootContext())
    assert root is not None, errors

    first = bool(root.property("firstStillLoading"))
    second = bool(root.property("secondStillLoading"))
    print(f"{PROBE_MARKER} first={str(first).lower()} second={str(second).lower()}")
    assert first is False
    assert second is False

    root.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--probe"]:
        raise SystemExit("usage: python -m tests.test_diff_viewer_repeat_loading_qml --probe")
    raise SystemExit(_run_probe())
