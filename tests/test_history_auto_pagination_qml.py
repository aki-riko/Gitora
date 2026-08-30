# coding: utf-8
"""真实滚轮触底后自动分页探针。"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from tests.test_history_scroll_qml import (
    ROOT,
    _build_repo,
    _create_scene,
    _probe_environment,
    _pump,
    _send_wheel,
    _wait_until,
)


def test_history_scroll_auto_paginates_after_reaching_real_end() -> None:
    """真实滚到末尾后必须自动请求下一页,而不是停在首个分页。"""
    with tempfile.TemporaryDirectory(prefix="gitora-history-auto-page-") as temp_dir:
        repo = _build_repo(Path(temp_dir), count=90)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_history_auto_pagination_qml",
                "--probe",
                str(repo),
            ],
            cwd=str(ROOT),
            env=_probe_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=45,
            check=False,
        )
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert "[HISTORY_AUTO_PAGE_QML_PROBE]" in result.stdout, diagnostic


def _run_probe(repo: Path) -> int:
    from PySide6.QtCore import QMetaObject, QObject, Qt
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
            and root.property("probeCommitCount") == 30,
            timeout=10.0,
        ):
            raise AssertionError(
                {
                    "phase": "initial_page",
                    "count": root.property("probeCommitCount"),
                    "loading": root.property("probeLoading"),
                    "has_more": root.property("probeHasMore"),
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
        if not _wait_until(
            lambda: float(helper.property("maxScroll"))
            > float(helper.property("minScroll"))
        ):
            raise AssertionError("timeline did not become scrollable")
        if not QMetaObject.invokeMethod(
            helper, "scrollToStart", Qt.ConnectionType.DirectConnection
        ):
            raise AssertionError("cannot reset timeline to start")
        if not _wait_until(
            lambda: abs(
                float(viewport.property("contentY"))
                - float(helper.property("minScroll"))
            ) <= 0.5
            and not helper.property("isOvershot"),
            timeout=10.0,
        ):
            raise AssertionError("timeline did not settle at start")
        # Use the same wheel path as the desktop client instead of calling the
        # helper's programmatic scroll API. 用桌面端相同的滚轮路径触底。
        for _ in range(80):
            _send_wheel(root, viewport, -120)
            _pump(35)
            if float(viewport.property("contentY")) >= float(
                helper.property("maxScroll")
            ) - 1:
                break
        if not _wait_until(
            lambda: abs(
                float(viewport.property("contentY"))
                - float(helper.property("maxScroll"))
            ) <= 0.5
            and not helper.property("isOvershot"),
            timeout=10.0,
        ):
            raise AssertionError(
                {
                    "phase": "wheel_to_end",
                    "content_y": viewport.property("contentY"),
                    "max": helper.property("maxScroll"),
                    "overshot": helper.property("isOvershot"),
                }
            )
        for expected_count in (60, 90):
            if not _wait_until(
                lambda expected=expected_count: root.property("probeCommitCount")
                >= expected
                and not root.property("probeLoading"),
                timeout=8.0,
            ):
                raise AssertionError(
                    {
                        "phase": "auto_page",
                        "expected": expected_count,
                        "count": root.property("probeCommitCount"),
                        "loading": root.property("probeLoading"),
                        "has_more": root.property("probeHasMore"),
                        "content_y": viewport.property("contentY"),
                        "max": helper.property("maxScroll"),
                    }
                )
            if expected_count == 90:
                break
            # The append increases maxScroll. Continue through the new page using
            # real wheel input so the next threshold is exercised as well.
            for _ in range(80):
                _send_wheel(root, viewport, -120)
                _pump(35)
                if float(viewport.property("contentY")) >= float(
                    helper.property("maxScroll")
                ) - 1:
                    break
        print(
            "[HISTORY_AUTO_PAGE_QML_PROBE] "
            f"count={root.property('probeCommitCount')}"
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
        raise SystemExit("usage: test_history_auto_pagination_qml.py --probe REPO")
    raise SystemExit(_run_probe(Path(sys.argv[2])))
