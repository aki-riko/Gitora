# coding: utf-8
"""真实 QML 分支页在离页期间切换分支后应刷新。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import build_branched_repo, run_git


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[BRANCH_MUTATION_REFRESH_QML_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "views"

Window {
    id: root
    width: 1280
    height: 800
    visible: true
    color: Fluent.Enums.backgroundColor

    readonly property string probeCurrentBranch: branchView.currentBranch

    Item {
        id: pageHost
        objectName: "branchPageHost"
        anchors.fill: parent

        BranchView {
            id: branchView
            objectName: "branchView"
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


def test_real_branch_page_refreshes_after_hidden_checkout() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-branch-refresh-") as temp_dir:
        repo, _hashes = build_branched_repo(Path(temp_dir))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_branch_mutation_refresh_qml",
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
        assert f"{PROBE_MARKER} branches=master,side,master" in result.stdout


def _run_probe(repo: Path) -> int:
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge
    from tests.test_history_scope_qml import _pump, _wait_until

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    bridge._poll_timer.stop()
    if not bridge._svc.set_repo_path(str(repo), emit_status=False):
        raise AssertionError(f"cannot open repository: {repo}")
    engine.rootContext().setContextProperty("GitBridge", bridge)

    component = QQmlComponent(engine)
    component.setData(
        PROBE_SOURCE,
        QUrl.fromLocalFile(
            str(ROOT / "app_qml" / "qml" / "BranchMutationProbe.qml")
        ),
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

    page_host = root.findChild(QObject, "branchPageHost")
    if page_host is None:
        raise AssertionError("missing branch page host")

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    def button_states() -> dict[str, str]:
        return {
            str(button.property("branchName")): str(button.property("text"))
            for button in visual_items(root.contentItem())
            if button.objectName() == "localBranchActionButton"
        }

    def wait_for_branch(branch: str) -> None:
        def matches() -> bool:
            states = button_states()
            return (
                root.property("probeCurrentBranch") == branch
                and states.get(branch) == "管理"
                and states.get("side" if branch == "master" else "master")
                == "切换"
            )

        if not _wait_until(matches):
            raise AssertionError(
                {
                    "expected_branch": branch,
                    "actual_branch": root.property("probeCurrentBranch"),
                    "button_states": button_states(),
                }
            )

    wait_for_branch("master")
    initial_branch = str(root.property("probeCurrentBranch"))

    page_host.setProperty("visible", False)
    run_git(repo, "checkout", "side")
    page_host.setProperty("visible", True)
    wait_for_branch("side")
    side_branch = str(root.property("probeCurrentBranch"))

    page_host.setProperty("visible", False)
    run_git(repo, "checkout", "master")
    page_host.setProperty("visible", True)
    wait_for_branch("master")
    restored_branch = str(root.property("probeCurrentBranch"))

    print(
        f"{PROBE_MARKER} "
        f"branches={initial_branch},{side_branch},{restored_branch}"
    )
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
            "usage: test_branch_mutation_refresh_qml.py --probe REPO"
        )
    raise SystemExit(_run_probe(Path(sys.argv[2])))
