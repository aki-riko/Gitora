# coding: utf-8
"""主线程停顿观测（StallTraceProbe）的口径与接线测试。

观测默认关闭；打开时按固定间隔打点并在超过阈值时记录一行停顿，
用来把「长时间运行后响应变慢」定位到主线程停顿而不是靠猜。
"""
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


def _probe_source() -> bytes:
    component_url = COMPONENT_DIR.as_uri()
    return f"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import \"{component_url}\"

Window {{
    width: 400
    height: 200
    visible: false

    property int intervalMs: 100
    property int thresholdMs: 250

    StallTraceProbe {{
        id: probe
        objectName: \"stallTraceProbe\"
        intervalMs: parent.intervalMs
        thresholdMs: parent.thresholdMs
    }}
}}
""".encode("utf-8")


def _create_scene():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from prismqml import qml_path

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(qml_path().parent))
    component = QQmlComponent(engine)
    component.setData(
        _probe_source(),
        QUrl.fromLocalFile(str(ROOT / "tests" / "StallTraceProbe.qml")),
    )
    deadline = time.monotonic() + 5
    while (
        component.status() == QQmlComponent.Status.Loading
        and time.monotonic() < deadline
    ):
        _pump(20)
    assert component.status() == QQmlComponent.Status.Ready, component.errors()
    window = component.create()
    assert window is not None, component.errors()
    _pump(20)
    probe = window.findChild(object, "stallTraceProbe")
    assert probe is not None
    return app, engine, component, window, probe


def _destroy_scene(app, engine, component, window) -> None:
    window.destroy()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()


def test_stall_probe_is_off_by_default_and_records_only_long_gaps() -> None:
    app, engine, component, window, probe = _create_scene()
    try:
        # 默认关闭：定时器不运行，也不应产生任何记录。
        assert probe.property("enabled") is False
        assert probe.property("ticking") is False

        assert probe.property("stallCount") == 0
        # 首次打点只建立基线。
        assert probe.recordTick(1000.0) == 0
        # 正常间隔不记录。
        assert probe.recordTick(1100.0) == 100.0
        assert probe.property("stallCount") == 0
        assert probe.property("lastStallText") == ""

        # 超过阈值的间隔必须被记录，且带上间隔与阈值。
        assert probe.recordTick(1700.0) == 600.0
        assert probe.property("stallCount") == 1
        stall_text = str(probe.property("lastStallText"))
        assert stall_text.startswith("[STALL_TRACE] #1")
        assert "gap=600ms" in stall_text
        assert "threshold=250" in stall_text

        # 再次超阈值继续累计，短间隔不累加。
        assert probe.recordTick(1800.0) == 100.0
        assert probe.property("stallCount") == 1
        probe.recordTick(2600.0)
        assert probe.property("stallCount") == 2
    finally:
        _destroy_scene(app, engine, component, window)


def test_stall_probe_timer_runs_only_when_enabled() -> None:
    app, engine, component, window, probe = _create_scene()
    try:
        probe.setProperty("enabled", True)
        _pump(30)
        assert probe.property("ticking") is True
        assert probe.property("lastTickMs") > 0
        probe.setProperty("enabled", False)
        _pump(30)
        assert probe.property("ticking") is False
    finally:
        _destroy_scene(app, engine, component, window)


def test_stall_probe_emits_through_bridge_so_it_lands_in_app_log() -> None:
    """QML console 不落 Gitora 日志：观测必须经桥写应用日志。"""
    app, engine, component, window, probe = _create_scene()
    try:
        from PySide6.QtCore import QObject, Slot

        class _RecordingBridge(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.messages: list[str] = []

            @Slot(str)
            def logStallTrace(self, message: str) -> None:
                self.messages.append(str(message))

        bridge = _RecordingBridge()
        probe.setProperty("renderBridge", bridge)
        probe.recordTick(1000.0)
        probe.recordTick(1500.0)
        assert bridge.messages and bridge.messages[-1].startswith("[STALL_TRACE] #1")
    finally:
        _destroy_scene(app, engine, component, window)


def test_main_wires_stall_trace_flag_from_environment() -> None:
    main_source = (ROOT / "app_qml" / "qml" / "main.qml").read_text(
        encoding="utf-8"
    )
    entry_source = (ROOT / "app_qml" / "main_qml.py").read_text(encoding="utf-8")

    assert "StallTraceProbe" in main_source
    assert "GitoraStallTraceEnabled" in main_source
    assert '"GitoraStallTraceEnabled"' in entry_source
    assert 'GITORA_STALL_TRACE' in entry_source
    # 默认关闭：是否运行完全由环境开关决定。
    assert 'running: probe.enabled' in (
        COMPONENT_DIR / "StallTraceProbe.qml"
    ).read_text(encoding="utf-8")
