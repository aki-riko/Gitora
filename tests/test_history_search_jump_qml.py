# coding: utf-8
"""在真实 QML 历史页验证搜索结果“跳转”:清除搜索、补全时间线并定位选中。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests.git_test_utils import init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[HISTORY_SEARCH_JUMP_QML_PROBE]"
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
    readonly property bool probeSearchMode: historyView.searchMode
    readonly property string probeSelectedHash:
        historyView.selectedCommit ? historyView.selectedCommit.hash : ""
    readonly property string probePendingHash: historyView.pendingJumpHash

    function startSearch() {
        historyView.doSearch("needle")
    }

    Item {
        anchors.fill: parent

        HistoryView {
            id: historyView
            objectName: "historySearchJumpView"
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


def _commit_at(
    repo: Path, index: int, date_text: str, message: str | None = None
) -> None:
    write_file(repo, "history.txt", f"{index}\n")
    run_git(repo, "add", "-A")
    environment = os.environ.copy()
    environment["GIT_AUTHOR_DATE"] = date_text
    environment["GIT_COMMITTER_DATE"] = date_text
    result = subprocess.run(
        ["git", "commit", "-m", message or f"commit {index}"],
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


def _build_repo_with_needle(root: Path) -> tuple[Path, str]:
    repo = init_repo(root / "repo")
    needle_hash = ""
    for index in range(90):
        message = "needle: 搜索跳转目标提交" if index == 45 else None
        _commit_at(
            repo,
            index,
            f"2026-07-{26 + index // 30:02d}T12:{index % 60:02d}:00+0800",
            message,
        )
        if index == 45:
            needle_hash = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, needle_hash


def test_search_jump_clears_search_and_positions_target_commit() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-history-search-jump-") as temp_dir:
        repo, needle_hash = _build_repo_with_needle(Path(temp_dir))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_history_search_jump_qml",
                "--probe",
                str(repo),
                needle_hash,
            ],
            cwd=str(ROOT),
            env=_probe_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert PROBE_MARKER in result.stdout, diagnostic
        assert "commits=90" in result.stdout, diagnostic


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _wait_until(predicate, timeout: float = 10.0) -> bool:
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
        str(ROOT / "app_qml" / "qml" / "HistorySearchJumpProbe.qml")
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


def _find_action_item(window):
    """ListView 委托不在窗口的 QObject 子树里,findChild 找不到,必须走可视树。"""
    from PySide6.QtQuick import QQuickItem

    def walk(item):
        if item.objectName() == "timelineCardAction":
            return item
        for child in item.childItems():
            found = walk(child)
            if found is not None:
                return found
        return None

    return walk(window.contentItem())


def _run_probe(repo: Path, needle_hash: str) -> int:
    from PySide6.QtCore import QObject, QMetaObject, QPointF, Qt
    from PySide6.QtGui import QCursor
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
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
            root, "startSearch", Qt.ConnectionType.DirectConnection
        ):
            raise AssertionError("cannot invoke search")
        if not _wait_until(
            lambda: root.property("probeSearchMode")
            and root.property("probeCommitCount") == 1
        ):
            raise AssertionError(
                {
                    "phase": "search",
                    "searchMode": root.property("probeSearchMode"),
                    "count": root.property("probeCommitCount"),
                }
            )

        # 搜索结果卡片必须渲染出"跳转"动作链接。
        if not _wait_until(lambda: _find_action_item(root) is not None):
            raise AssertionError({"phase": "action-link", "found": False})
        action = _find_action_item(root)
        center = action.mapToScene(
            QPointF(action.width() / 2, action.height() / 2)
        ).toPoint()
        QTest.mouseClick(
            root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center
        )

        # 点击后:搜索退出、时间线补全 90 条、跳转状态清理、目标提交选中。
        if not _wait_until(
            lambda: not root.property("probeSearchMode")
            and not root.property("probeLoading")
            and root.property("probeCommitCount") == 90
            and root.property("probePendingHash") == ""
            and root.property("probeSelectedHash") == needle_hash
        ):
            raise AssertionError(
                {
                    "phase": "jump",
                    "searchMode": root.property("probeSearchMode"),
                    "loading": root.property("probeLoading"),
                    "count": root.property("probeCommitCount"),
                    "pending": root.property("probePendingHash"),
                    "selected": root.property("probeSelectedHash"),
                    "needle": needle_hash,
                }
            )

        history = root.findChild(QObject, "historySearchJumpView")
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
    if len(sys.argv) != 4 or sys.argv[1] != "--probe":
        raise SystemExit(
            "usage: test_history_search_jump_qml.py --probe REPO NEEDLE_HASH"
        )
    raise SystemExit(_run_probe(Path(sys.argv[2]), sys.argv[3]))
