# coding: utf-8
"""真实 QML 历史页在分支切换后刷新，且分栏不递归。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import build_branched_repo


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[HISTORY_MUTATION_REFRESH_QML_PROBE]"


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


def test_real_branch_switch_refreshes_history_without_split_recursion() -> None:
    with tempfile.TemporaryDirectory(
        prefix="gitora-history-mutation-refresh-"
    ) as temp_dir:
        repo, _hashes = build_branched_repo(Path(temp_dir))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_history_mutation_refresh_qml",
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
        assert "counts=4,2,4 stack_overflows=0" in result.stdout, diagnostic


def _run_probe(repo: Path) -> int:
    from PySide6.QtCore import qInstallMessageHandler
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge
    from tests.test_history_scope_qml import _create_scene, _wait_until

    stack_overflows: list[str] = []

    def message_handler(_kind, _context, message: str) -> None:
        if "Maximum call stack size exceeded" in message:
            stack_overflows.append(message)

    qInstallMessageHandler(message_handler)
    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    if not bridge._svc.set_repo_path(str(repo), emit_status=False):
        raise AssertionError(f"cannot open repository: {repo}")
    engine.rootContext().setContextProperty("GitBridge", bridge)

    component, root = _create_scene(engine)

    def wait_for_count(count: int) -> None:
        if not _wait_until(
            lambda: not root.property("probeLoading")
            and root.property("probeCommitCount") == count
        ):
            raise AssertionError(
                {
                    "expected_count": count,
                    "actual_count": root.property("probeCommitCount"),
                    "loading": root.property("probeLoading"),
                }
            )

    def checkout(branch: str) -> None:
        finished: list[bool] = []
        results: list[object] = []
        task = bridge.checkoutBranch(branch)
        task.succeeded.connect(results.append)
        task.finished.connect(lambda: finished.append(True))
        if not _wait_until(lambda: bool(finished)):
            raise AssertionError(f"checkout {branch} did not finish")
        if not results or not results[-1][0]:
            raise AssertionError({"branch": branch, "results": results})

    wait_for_count(4)
    initial_count = int(root.property("probeCommitCount"))
    checkout("side")
    wait_for_count(2)
    side_count = int(root.property("probeCommitCount"))
    checkout("master")
    wait_for_count(4)
    restored_count = int(root.property("probeCommitCount"))

    root.setWidth(650)
    app.processEvents()
    root.setWidth(1400)
    app.processEvents()

    print(
        f"{PROBE_MARKER} counts={initial_count},{side_count},{restored_count} "
        f"stack_overflows={len(stack_overflows)}"
    )
    root.close()
    root.deleteLater()
    component.deleteLater()
    bridge.deleteLater()
    engine.deleteLater()
    app.processEvents()
    qInstallMessageHandler(None)
    return 0 if not stack_overflows else 1


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--probe":
        raise SystemExit(
            "usage: test_history_mutation_refresh_qml.py --probe REPO"
        )
    raise SystemExit(_run_probe(Path(sys.argv[2])))
