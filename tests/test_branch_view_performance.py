# coding: utf-8
"""分支页的大列表应使用可复用的虚拟滚动列表。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[BRANCH_VIRTUALIZATION_QML_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "views"

Window {
    width: 1280
    height: 900
    visible: true
    color: Fluent.Enums.backgroundColor

    BranchView {
        id: branchView
        objectName: "branchView"
        anchors.fill: parent
    }
}
"""


def test_branch_page_uses_one_virtualized_list_without_nesting() -> None:
    source = (ROOT / "app_qml" / "qml" / "views" / "BranchView.qml").read_text(
        encoding="utf-8"
    )

    assert source.count("Fluent.ScrollArea {") == 1
    assert source.count("type: Fluent.Enums.scroll.type_list") == 1
    assert source.count("reuseItems: true") == 1
    assert source.count("listCacheBuffer: root.branchItemHeight * 2") == 1
    assert source.count("model: root.branchRows") == 1
    assert "Repeater {" not in source
    assert "ListModel {" not in source
    assert 'objectName: "branchList"' in source
    assert 'objectName: "localBranchList"' not in source
    assert 'objectName: "remoteBranchList"' not in source


def test_branch_rows_lazy_load_lightweight_actions_and_share_one_menu() -> None:
    delegate_source = (
        ROOT / "app_qml" / "qml" / "components" / "BranchRowDelegate.qml"
    ).read_text(encoding="utf-8")
    menu_source = (
        ROOT / "app_qml" / "qml" / "components" / "BranchActionsMenu.qml"
    ).read_text(encoding="utf-8")
    view_source = (
        ROOT / "app_qml" / "qml" / "views" / "BranchView.qml"
    ).read_text(encoding="utf-8")

    assert "HoverHandler {" in delegate_source
    assert "rowHover.hovered || control.menuPinned" in delegate_source
    assert delegate_source.count("Fluent.Button {") == 2
    assert 'objectName: "branchMoreButton"' in delegate_source
    assert "menuItems:" not in delegate_source
    assert "feature_split" not in delegate_source
    assert "feature_dropdown" not in delegate_source
    assert view_source.count("BranchActionsMenu {") == 1
    assert menu_source.count("Fluent.MenuCore {") == 1
    assert "useInWindowPopup: true" in menu_source


def test_branch_sections_share_the_same_model_reset() -> None:
    source = (ROOT / "app_qml" / "qml" / "views" / "BranchView.qml").read_text(
        encoding="utf-8"
    )

    assert 'root._sectionRow("本地分支")' in source
    assert 'root._sectionRow("远程分支")' in source
    assert "root.branchRows = rows" in source
    assert "rows = rows.concat(localRows)" in source
    assert "rows = rows.concat([root._sectionRow" in source


def test_real_large_branch_set_keeps_qml_delegates_bounded() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-branch-virtualization-") as temp_dir:
        repo = _build_large_branch_repo(Path(temp_dir))
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_branch_view_performance",
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
        assert f"{PROBE_MARKER} branches=121" in result.stdout, diagnostic


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


def _build_large_branch_repo(root: Path) -> Path:
    repo = init_repo(root / "repo")
    write_file(repo, "root.txt", "root\n")
    commit_all(repo, "initial")
    for index in range(120):
        run_git(
            repo,
            "update-ref",
            f"refs/remotes/origin/perf-{index:03d}",
            "HEAD",
        )
    return repo


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
        QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "BranchVirtualizationProbe.qml")),
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

    branch_view = root.findChild(QObject, "branchView")
    branch_list = root.findChild(QObject, "branchList")
    if branch_view is None or branch_list is None:
        raise AssertionError("missing branch view or virtual list")
    if not _wait_until(
        lambda: branch_view.property("branchCount") == 121
        and branch_list.property("count") == 123
    ):
        raise AssertionError(
            {
                "branch_count": branch_view.property("branchCount"),
                "row_count": branch_list.property("count"),
            }
        )

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    _pump(750)
    items = list(visual_items(root.contentItem()))
    rendered = sum(
        1
        for item in items
        if item.objectName() == "branchRowDelegate"
    )
    if rendered <= 0 or rendered >= 40:
        raise AssertionError(f"unexpected rendered delegate count={rendered}")
    action_buttons = sum(
        1
        for item in items
        if item.objectName() in {
            "localBranchActionButton",
            "remoteBranchActionButton",
            "branchMoreButton",
        }
    )
    if action_buttons != 0:
        raise AssertionError(
            f"off-hover branch actions were eagerly loaded={action_buttons}"
        )
    window_count = len(app.allWindows())
    if window_count > 3:
        raise AssertionError(f"too many branch-page windows={window_count}")

    print(
        f"{PROBE_MARKER} branches={branch_view.property('branchCount')} "
        f"rows={branch_list.property('count')} rendered={rendered} "
        f"actions={action_buttons} windows={window_count}"
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
        raise SystemExit("usage: test_branch_view_performance.py --probe REPO")
    raise SystemExit(_run_probe(Path(sys.argv[2])))
