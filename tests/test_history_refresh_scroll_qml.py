# coding: utf-8
"""真实历史页刷新期间不应强制重定位滚动位置。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests.git_test_utils import commit_all, init_repo, write_file


ROOT = Path(__file__).resolve().parents[1]
MARKER = "[HISTORY_REFRESH_SCROLL_QML_PROBE]"
QML_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML
import "views"

Window {
    id: root
    width: 1400
    height: 850
    visible: true

    readonly property int commitCount: history.allCommits.length
    readonly property bool loading: history.loading
    readonly property bool pendingLog: history.timelinePendingLog !== null

    Item {
        anchors.fill: parent
        HistoryView {
            id: history
            objectName: "historyRefreshScrollView"
            anchors.fill: parent
        }
    }
}
"""


def _env() -> dict[str, str]:
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
    if not QApplication.sendEvent(window, event) or not event.isAccepted():
        raise AssertionError("wheel event was not accepted")


def _create_scene(engine):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    component = QQmlComponent(engine)
    component.setData(
        QML_SOURCE,
        QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "HistoryRefreshScrollProbe.qml")),
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


def _run_probe(repo: Path) -> int:
    from PySide6.QtCore import QObject, QMetaObject, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge, _commit_to_dict

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    if not bridge._svc.set_repo_path(str(repo), emit_status=False):
        raise AssertionError(f"cannot open repository: {repo}")
    engine.rootContext().setContextProperty("GitBridge", bridge)
    component, root = _create_scene(engine)
    try:
        if not _wait_until(
            lambda: not root.property("loading")
            and root.property("commitCount") == 30
        ):
            raise AssertionError("initial history page did not load")
        history = root.findChild(QObject, "historyRefreshScrollView")
        viewport = history.findChild(QObject, "timelineVirtualViewport")
        helper = next(
            item
            for item in history.findChildren(QObject)
            if "SmoothScrollHelper" in item.metaObject().className()
            and item.parent() is viewport
        )
        history.setProperty("hasMore", False)
        if not _wait_until(
            lambda: float(helper.property("maxScroll"))
            > float(helper.property("minScroll"))
        ):
            raise AssertionError("history timeline is not scrollable")
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
        _pump(250)

        first_page = [
            _commit_to_dict(commit)
            for commit in bridge._svc.get_graph_log_at(str(repo), 30, 0, False)
        ]
        samples: list[float] = []
        viewport.contentYChanged.connect(
            lambda: samples.append(float(viewport.property("contentY")))
        )
        _send_wheel(root, viewport, 120)
        if not _wait_until(lambda: bool(samples), timeout=1.0):
            raise AssertionError("timeline did not move after wheel input")

        history.setProperty("refreshing", True)
        history.setProperty("loading", True)
        history.setProperty("refreshCount", 30)
        bridge.logReady.emit(str(repo), 0, first_page)
        if not root.property("pendingLog") or root.property("commitCount") != 30:
            raise AssertionError(
                {
                    "phase": "refresh_applied_during_wheel",
                    "count": root.property("commitCount"),
                    "pending": root.property("pendingLog"),
                }
            )

        for _ in range(20):
            before = len(samples)
            _send_wheel(root, viewport, 120)
            _pump(40)
            outward = samples[before:]
            yanks = [
                (index, outward[index - 1], outward[index])
                for index in range(1, len(outward))
                if outward[index] > outward[index - 1] + 20
            ]
            if yanks or root.property("commitCount") != 30:
                raise AssertionError(
                    {
                        "phase": "refresh_repositioned_during_wheel",
                        "yanks": yanks,
                        "count": root.property("commitCount"),
                    }
                )

        if not _wait_until(
            lambda: not root.property("pendingLog")
            and not root.property("loading"),
            timeout=5.0,
        ):
            raise AssertionError(
                {
                    "phase": "refresh_after_wheel",
                    "pending": root.property("pendingLog"),
                    "loading": root.property("loading"),
                }
            )
        print(
            f"{MARKER} count={root.property('commitCount')} "
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


def test_real_history_refresh_waits_until_wheel_stops() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-history-refresh-scroll-") as temp_dir:
        repo = _build_repo(Path(temp_dir))
        result = subprocess.run(
            [sys.executable, "-m", "tests.test_history_refresh_scroll_qml", "--probe", str(repo)],
            cwd=str(ROOT),
            env=_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            check=False,
        )
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert MARKER in result.stdout, diagnostic


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--probe":
        raise SystemExit("usage: test_history_refresh_scroll_qml.py --probe REPO")
    raise SystemExit(_run_probe(Path(sys.argv[2])))
