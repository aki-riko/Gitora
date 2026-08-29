# coding: utf-8
"""真实历史页连续滚轮轨迹探针。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests.git_test_utils import commit_all, init_repo, write_file


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[HISTORY_SCROLL_QML_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "views"

Window {
    id: root
    width: 1400
    height: 850
    visible: true

    readonly property int probeCommitCount: historyView.allCommits.length
    readonly property bool probeLoading: historyView.loading
    readonly property bool probePendingLog: !!historyView.timelinePendingLog
    readonly property bool probeMotionObserved: historyView.timelineMotionObserved
    readonly property bool probeViewportReady: !!historyView.timelineViewport
    readonly property double probeLastMotionAt: historyView.timelineLastMotionAt
    readonly property double probeLastWheelAt: historyView.timelineLastWheelAt
    readonly property int probeQuietPeriod: historyView.timelineQuietPeriod
    property var injectedLogBatch: []

    function refreshTimelineData() {
        historyView.refreshIncrementally()
    }

    function injectNextTimelinePage() {
        historyView._handleLogReady(
            GitBridge.repoPath, 30, injectedLogBatch
        )
    }

    Item {
        anchors.fill: parent

        HistoryView {
            id: historyView
            objectName: "historyScrollView"
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


def _build_repo(root: Path, count: int = 90) -> Path:
    repo = init_repo(root / "repo")
    for index in range(count):
        write_file(repo, "history.txt", f"{index}\n")
        commit_all(repo, f"commit {index}")
    return repo


def test_history_scroll_probe_runs_against_real_commit_history() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-history-scroll-") as temp_dir:
        repo = _build_repo(Path(temp_dir))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_history_scroll_qml",
                "--probe",
                str(repo),
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


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _wait_until(predicate, timeout: float = 8.0) -> bool:
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
    component.setData(
        PROBE_SOURCE,
        QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "HistoryScrollProbe.qml")),
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


def _send_wheel(window, item, delta: int) -> None:
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    position = item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
    global_position = QPointF(window.x() + position.x(), window.y() + position.y())
    event = QWheelEvent(
        position,
        global_position,
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    if not QApplication.sendEvent(window, event):
        raise AssertionError("wheel event was not delivered")
    if not event.isAccepted():
        raise AssertionError("wheel event was not accepted")


def _run_probe(repo: Path) -> int:
    from PySide6.QtCore import QMetaObject, QObject, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    from app_qml.backend.git_bridge import GitBridge

    bridge = GitBridge()
    bridge._poll_timer.stop()
    if not bridge._svc.set_repo_path(str(repo), emit_status=False):
        raise AssertionError(f"cannot open repository: {repo}")
    engine.rootContext().setContextProperty("GitBridge", bridge)

    component, root = _create_scene(engine)
    try:
        from app_qml.backend.git_bridge import _commit_to_dict

        second_page = [
            _commit_to_dict(commit)
            for commit in bridge._svc.get_graph_log_at(str(repo), 30, 30, False)
        ]
        if len(second_page) != 30:
            raise AssertionError({"second_page_count": len(second_page)})
        if not root.setProperty("injectedLogBatch", second_page):
            raise AssertionError("cannot inject the real second history page")
        if not _wait_until(
            lambda: not root.property("probeLoading")
            and root.property("probeCommitCount") == 30
        ):
            raise AssertionError(
                {
                    "loading": root.property("probeLoading"),
                    "count": root.property("probeCommitCount"),
                }
            )

        history = root.findChild(QObject, "historyScrollView")
        viewport = history.findChild(QObject, "timelineVirtualViewport")
        helper = next(
            item
            for item in history.findChildren(QObject)
            if "SmoothScrollHelper" in item.metaObject().className()
            and item.parent() is viewport
        )
        if not _wait_until(lambda: root.property("probeViewportReady"), timeout=2.0):
            raise AssertionError("history view did not acquire its timeline viewport")
        history.setProperty("hasMore", False)
        if not _wait_until(
            lambda: float(viewport.property("contentHeight"))
            > float(viewport.property("height"))
            and float(helper.property("maxScroll"))
            > float(helper.property("minScroll"))
        ):
            raise AssertionError(
                {
                    "content_height": viewport.property("contentHeight"),
                    "height": viewport.property("height"),
                    "min": helper.property("minScroll"),
                    "max": helper.property("maxScroll"),
                }
            )
        if not QMetaObject.invokeMethod(
            helper, "scrollToEnd", Qt.ConnectionType.DirectConnection
        ):
            raise AssertionError("cannot position timeline at end")
        if not _wait_until(
            lambda: abs(
                float(viewport.property("contentY"))
                - float(helper.property("maxScroll"))
            )
            <= 0.5
            and not helper.property("isOvershot")
        ):
            raise AssertionError("timeline did not settle at end")
        _pump(300)

        pagination_samples: list[float] = []
        viewport.contentYChanged.connect(
            lambda: pagination_samples.append(float(viewport.property("contentY")))
        )
        before_motion = float(root.property("probeLastMotionAt"))
        before_wheel = float(root.property("probeLastWheelAt"))
        _send_wheel(root, viewport, 120)
        if not _wait_until(
            lambda: float(root.property("probeLastMotionAt")) > before_motion
            and float(root.property("probeLastWheelAt")) > before_wheel
            and bool(pagination_samples),
            timeout=1.0,
        ):
            raise AssertionError(
                {
                    "phase": "first_wheel_frame",
                    "content_y": viewport.property("contentY"),
                    "target": helper.property("targetPos"),
                    "smooth": helper.property("smoothPos"),
                    "min": helper.property("minScroll"),
                    "max": helper.property("maxScroll"),
                    "motion": root.property("probeMotionObserved"),
                    "samples": pagination_samples,
                }
            )
        if not QMetaObject.invokeMethod(
            root, "injectNextTimelinePage", Qt.ConnectionType.DirectConnection
        ):
            raise AssertionError("cannot apply the real second history page")
        if not root.property("probePendingLog") or root.property("probeCommitCount") != 30:
            raise AssertionError(
                {
                    "phase": "pagination_not_deferred",
                    "count": root.property("probeCommitCount"),
                    "pending": root.property("probePendingLog"),
                    "last_motion": root.property("probeLastMotionAt"),
                    "last_wheel": root.property("probeLastWheelAt"),
                    "quiet": root.property("probeQuietPeriod"),
                }
            )
        for _ in range(7):
            _pump(40)
            before_wheel = float(root.property("probeLastWheelAt"))
            _send_wheel(root, viewport, 120)
            if not _wait_until(
                lambda: float(root.property("probeLastWheelAt")) > before_wheel,
                timeout=0.5,
            ):
                raise AssertionError("business wheel observer missed an input event")
        if not _wait_until(lambda: root.property("probePendingLog"), timeout=2.0):
            raise AssertionError(
                {
                    "phase": "pagination_pending",
                    "count": root.property("probeCommitCount"),
                    "loading": root.property("probeLoading"),
                    "samples": pagination_samples,
                }
            )
        if root.property("probeCommitCount") != 30:
            raise AssertionError(
                {
                    "phase": "pagination_applied_during_motion",
                    "count": root.property("probeCommitCount"),
                    "samples": pagination_samples,
                }
            )
        pagination_yanks = [
            (index, pagination_samples[index - 1], pagination_samples[index])
            for index in range(1, len(pagination_samples))
            if pagination_samples[index] > pagination_samples[index - 1] + 20
        ]
        if pagination_yanks:
            raise AssertionError(
                {
                    "phase": "pagination_mid_burst_realign",
                    "yanks": pagination_yanks,
                }
            )
        if not _wait_until(
            lambda: root.property("probeCommitCount") == 60
            and not root.property("probeLoading"),
            timeout=4.0,
        ):
            raise AssertionError(
                {
                    "phase": "pagination_after_motion",
                    "count": root.property("probeCommitCount"),
                    "loading": root.property("probeLoading"),
                    "pending": root.property("probePendingLog"),
                    "samples": pagination_samples,
                }
            )
        history.setProperty("hasMore", False)

        if not QMetaObject.invokeMethod(
            helper, "scrollToStart", Qt.ConnectionType.DirectConnection
        ):
            raise AssertionError("cannot position timeline at start")
        if not _wait_until(
            lambda: abs(
                float(viewport.property("contentY"))
                - float(helper.property("minScroll"))
            )
            <= 0.5
            and not helper.property("isOvershot")
        ):
            raise AssertionError("timeline did not settle at start")
        _pump(1000)

        samples: list[float] = []
        viewport.contentYChanged.connect(
            lambda: samples.append(float(viewport.property("contentY")))
        )
        for wheel_index in range(6):
            _send_wheel(root, viewport, 120)
            _pump(40)
            if wheel_index == 0:
                if not QMetaObject.invokeMethod(
                    root, "refreshTimelineData", Qt.ConnectionType.DirectConnection
                ):
                    raise AssertionError("cannot refresh timeline data")
                _pump(20)
        if not _wait_until(
            lambda: abs(
                float(viewport.property("contentY"))
                - float(helper.property("minScroll"))
            )
            <= 0.5
            and not helper.property("isOvershot"),
            timeout=3.0,
        ):
            raise AssertionError(
                {
                    "phase": "settle",
                    "content_y": viewport.property("contentY"),
                    "min": helper.property("minScroll"),
                    "overshot": helper.property("isOvershot"),
                }
            )
        minimum = float(helper.property("minScroll"))
        maximum_overshoot = float(helper.property("_maxOvershoot"))
        if not any(value < minimum - 1 for value in samples):
            raise AssertionError({"phase": "overshoot", "samples": samples})
        if any(value < minimum - maximum_overshoot - 1 for value in samples):
            raise AssertionError(
                {
                    "phase": "overshoot_limit",
                    "minimum": minimum,
                    "maximum_overshoot": maximum_overshoot,
                    "samples": samples,
                }
            )
        lowest_index = min(range(len(samples)), key=samples.__getitem__)
        outward = samples[: lowest_index + 1]
        yanks = [
            (index, outward[index - 1], outward[index])
            for index in range(1, len(outward))
            if outward[index] > outward[index - 1] + 2
        ]
        if yanks:
            raise AssertionError({"phase": "mid_burst_realign", "yanks": yanks})
        print(
            f"{PROBE_MARKER} count={root.property('probeCommitCount')} "
            f"samples={','.join(f'{value:.1f}' for value in samples)}"
        )
    finally:
        root.close()
        root.deleteLater()
        component.deleteLater()
        bridge.deleteLater()
        engine.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--probe":
        raise SystemExit("usage: test_history_scroll_qml.py --probe REPO")
    raise SystemExit(_run_probe(Path(sys.argv[2])))
