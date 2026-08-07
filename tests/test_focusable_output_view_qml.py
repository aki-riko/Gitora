from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[FOCUSABLE_OUTPUT_VIEW_QML_PROBE]"

PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window

import PrismQML as Fluent
import "components"

Window {
    id: root
    width: 640
    height: 480
    visible: true

    property string longText: ""

    Component.onCompleted: {
        var lines = []
        for (var i = 0; i < 120; i++) lines.push("real-output-line-" + i)
        longText = lines.join("\\n")
    }

    Fluent.ScrollArea {
        id: outerScroll
        objectName: "outerScroll"
        anchors.fill: parent
        padding: 0

        Column {
            width: parent ? parent.width : 0

            Item { width: parent ? parent.width : 0; height: 160 }

            FocusableOutputView {
                id: outputView
                objectName: "outputView"
                width: parent ? parent.width : 0
                height: 220
                text: root.longText
                scrollPassthroughTarget: outerScroll
            }

            Item { width: parent ? parent.width : 0; height: 800 }
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


def test_focusable_output_view_routes_wheel_by_focus() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tests.test_focusable_output_view_qml", "--probe"],
        cwd=str(ROOT),
        env=_probe_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    assert f"{PROBE_MARKER} PASS" in result.stdout, diagnostic


def test_advanced_view_uses_focusable_output_views() -> None:
    advanced = (ROOT / "app_qml" / "qml" / "views" / "AdvancedView.qml").read_text(
        encoding="utf-8"
    )
    component = (
        ROOT / "app_qml" / "qml" / "components" / "FocusableOutputView.qml"
    ).read_text(encoding="utf-8")

    assert advanced.count("FocusableOutputView {") == 2
    assert advanced.count("scrollPassthroughTarget: advancedScrollArea") == 4
    assert 'objectName: "lfsOutputView"' in advanced
    assert 'objectName: "bisectOutputView"' in advanced
    assert "enabled: !outputText.activeFocus" in component
    assert "root._routeUnfocusedWheel(wheel)" in component
    assert "Fluent.ScrollArea" in component


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _send_wheel(window, item, angle_delta_y: int) -> None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QGuiApplication, QWheelEvent

    position = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    global_position = QPointF(window.mapToGlobal(position.toPoint()))
    event = QWheelEvent(
        position,
        global_position,
        QPoint(),
        QPoint(0, angle_delta_y),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate,
        False,
    )
    QGuiApplication.sendEvent(window, event)


def _run_probe() -> int:
    from PySide6.QtCore import QObject, QPointF, Qt, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    component = QQmlComponent(engine)
    component.setData(
        PROBE_SOURCE,
        QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "FocusableOutputViewProbe.qml")),
    )
    for _ in range(50):
        if component.status() != QQmlComponent.Status.Loading:
            break
        _pump(20)
    errors = [error.toString() for error in component.errors()]
    if component.status() != QQmlComponent.Status.Ready:
        raise AssertionError(errors)
    window = component.create(engine.rootContext())
    if window is None:
        raise AssertionError(errors)

    outer_scroll = window.findChild(QObject, "outerScroll")
    output_view = window.findChild(QObject, "outputView")
    output_text = window.findChild(QObject, "outputViewText")
    if outer_scroll is None or output_view is None or output_text is None:
        raise AssertionError(
            {
                "outer_scroll": outer_scroll,
                "output_view": output_view,
                "output_text": output_text,
            }
        )

    _pump(200)
    outer_before = float(outer_scroll.property("contentY"))
    inner_before = float(output_view.property("contentY"))
    _send_wheel(window, output_view, -120)
    _pump(400)
    outer_unfocused = float(outer_scroll.property("contentY"))
    inner_unfocused = float(output_view.property("contentY"))
    if outer_unfocused <= outer_before + 1 or abs(inner_unfocused - inner_before) > 1:
        raise AssertionError(
            {
                "phase": "unfocused",
                "outer_before": outer_before,
                "outer_after": outer_unfocused,
                "inner_before": inner_before,
                "inner_after": inner_unfocused,
            }
        )

    click_position = output_text.mapToScene(QPointF(20, 20)).toPoint()
    QTest.mouseClick(
        window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        click_position,
    )
    _pump(100)
    if not bool(output_view.property("focused")):
        raise AssertionError("output text did not gain focus")

    outer_focused_before = float(outer_scroll.property("contentY"))
    inner_focused_before = float(output_view.property("contentY"))
    _send_wheel(window, output_view, -120)
    _pump(400)
    outer_focused_after = float(outer_scroll.property("contentY"))
    inner_focused_after = float(output_view.property("contentY"))
    if (
        abs(outer_focused_after - outer_focused_before) > 1
        or inner_focused_after <= inner_focused_before + 1
    ):
        raise AssertionError(
            {
                "phase": "focused",
                "outer_before": outer_focused_before,
                "outer_after": outer_focused_after,
                "inner_before": inner_focused_before,
                "inner_after": inner_focused_after,
            }
        )

    print(
        f"{PROBE_MARKER} PASS "
        f"outer={outer_before:.1f}->{outer_unfocused:.1f}->"
        f"{outer_focused_after:.1f} "
        f"inner={inner_before:.1f}->{inner_unfocused:.1f}->"
        f"{inner_focused_after:.1f}"
    )
    window.close()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--probe"]:
        raise SystemExit("usage: test_focusable_output_view_qml.py --probe")
    raise SystemExit(_run_probe())
