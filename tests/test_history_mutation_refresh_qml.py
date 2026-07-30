# coding: utf-8
"""真实 QML 历史页在分支切换后刷新，且分栏不递归。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import build_branched_repo, run_git


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
        assert (
            "counts=4,2,4,2,4 branches=master,HEAD,master,side,master "
            "stack_overflows=0"
            in result.stdout
        ), diagnostic


def _run_probe(repo: Path) -> int:
    from PySide6.QtCore import QObject, qInstallMessageHandler
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

    def wait_for_state(count: int, branch: str) -> None:
        if not _wait_until(
            lambda: not root.property("probeLoading")
            and root.property("probeCommitCount") == count
            and root.property("probeCurrentBranch") == branch
        ):
            raise AssertionError(
                {
                    "expected_count": count,
                    "actual_count": root.property("probeCommitCount"),
                    "expected_branch": branch,
                    "actual_branch": root.property("probeCurrentBranch"),
                    "loading": root.property("probeLoading"),
                }
            )

    def run_task(task, description: str) -> None:
        finished: list[bool] = []
        results: list[object] = []
        task.succeeded.connect(results.append)
        task.finished.connect(lambda: finished.append(True))
        if not _wait_until(lambda: bool(finished)):
            raise AssertionError(f"{description} did not finish")
        if not results or not results[-1][0]:
            raise AssertionError({"description": description, "results": results})

    history_view = root.findChild(QObject, "historyScopeView")
    if history_view is None:
        raise AssertionError("missing history view")
    page_host = root.findChild(QObject, "historyScopePageHost")
    if page_host is None:
        raise AssertionError("missing history page host")

    wait_for_state(4, "master")
    initial_count = int(root.property("probeCommitCount"))
    initial_branch = str(root.property("probeCurrentBranch"))

    earlier_commit = run_git(repo, "rev-parse", "master~1").stdout.strip()
    run_task(bridge.checkoutCommit(earlier_commit), "checkout commit")
    wait_for_state(2, "HEAD")
    detached_count = int(root.property("probeCommitCount"))
    detached_branch = str(root.property("probeCurrentBranch"))

    run_task(bridge.checkoutBranch("master"), "checkout master")
    wait_for_state(4, "master")
    operated_count = int(root.property("probeCommitCount"))
    operated_branch = str(root.property("probeCurrentBranch"))

    page_host.setProperty("visible", False)
    run_git(repo, "checkout", "side")
    page_host.setProperty("visible", True)
    wait_for_state(2, "side")
    side_count = int(root.property("probeCommitCount"))
    side_branch = str(root.property("probeCurrentBranch"))

    page_host.setProperty("visible", False)
    run_git(repo, "checkout", "master")
    page_host.setProperty("visible", True)
    wait_for_state(4, "master")
    restored_count = int(root.property("probeCommitCount"))
    restored_branch = str(root.property("probeCurrentBranch"))

    root.setWidth(650)
    app.processEvents()
    root.setWidth(1400)
    app.processEvents()

    print(
        f"{PROBE_MARKER} counts={initial_count},{detached_count},"
        f"{operated_count},{side_count},{restored_count} "
        f"branches={initial_branch},{detached_branch},{operated_branch},"
        f"{side_branch},{restored_branch} "
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
