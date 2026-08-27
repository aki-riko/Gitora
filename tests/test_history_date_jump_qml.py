# coding: utf-8
"""在真实 QML 历史页验证日期选择后的分页与滚动定位。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests.git_test_utils import init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[HISTORY_DATE_JUMP_QML_PROBE]"
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
    readonly property string probePendingDate: historyView.pendingJumpDate

    function jumpToOlderDate() {
        historyView.jumpToDate(2026, 7, 24)
    }

    Item {
        anchors.fill: parent

        HistoryView {
            id: historyView
            objectName: "historyDateJumpView"
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


def _commit_at(repo: Path, index: int, date_text: str) -> None:
    write_file(repo, "history.txt", f"{index}\n")
    run_git(repo, "add", "-A")
    environment = os.environ.copy()
    environment["GIT_AUTHOR_DATE"] = date_text
    environment["GIT_COMMITTER_DATE"] = date_text
    result = subprocess.run(
        ["git", "commit", "-m", f"commit {index}"],
        cwd=str(repo),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)


def _build_dated_repo(root: Path) -> Path:
    repo = init_repo(root / "repo")
    for index in range(60):
        day = 24 if index < 30 else 25
        _commit_at(
            repo,
            index,
            f"2026-07-{day:02d}T12:{index % 60:02d}:00+0800",
        )
    return repo


def test_date_jump_loads_older_page_and_moves_real_timeline() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-history-date-jump-") as temp_dir:
        repo = _build_dated_repo(Path(temp_dir))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_history_date_jump_qml",
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
        assert "commits=60" in result.stdout, diagnostic


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
    base_url = QUrl.fromLocalFile(
        str(ROOT / "app_qml" / "qml" / "HistoryDateJumpProbe.qml")
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


def _run_probe(repo: Path) -> int:
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
    try:
        if not _wait_until(
            lambda: not root.property("probeLoading")
            and root.property("probeCommitCount") == 30
        ):
            raise AssertionError(
                {
                    "phase": "initial",
                    "loading": root.property("probeLoading"),
                    "count": root.property("probeCommitCount"),
                }
            )
        if not QMetaObject.invokeMethod(
            root, "jumpToOlderDate", Qt.ConnectionType.DirectConnection
        ):
            raise AssertionError("cannot invoke date jump")
        if not _wait_until(
            lambda: root.property("probeCommitCount") == 60
            and root.property("probePendingDate") == ""
        ):
            raise AssertionError(
                {
                    "phase": "jump",
                    "loading": root.property("probeLoading"),
                    "count": root.property("probeCommitCount"),
                    "pending": root.property("probePendingDate"),
                }
            )

        history = root.findChild(QObject, "historyDateJumpView")
        viewport = history.findChild(QObject, "timelineVirtualViewport")
        content_y = float(viewport.property("contentY"))
        if content_y <= 0:
            raise AssertionError({"contentY": content_y})
        print(
            f"{PROBE_MARKER} commits={root.property('probeCommitCount')} "
            f"rows={viewport.property('count')} contentY={content_y}"
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
        raise SystemExit(
            "usage: test_history_date_jump_qml.py --probe REPO"
        )
    raise SystemExit(_run_probe(Path(sys.argv[2])))
