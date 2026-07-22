# coding: utf-8
"""在独立 QML 进程中渲染真实分叉仓库的提交图。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import build_branched_repo


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_ENV = "GITORA_GRAPH_SCREENSHOT"
PROBE_MARKER = "[GRAPH_QML_PROBE]"
PROBE_SOURCE = b"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "components"

Window {
    id: root

    readonly property int probeLaneCount: graphModel.laneCount
    readonly property int probeCardCount: _cardCount(graphModel.items)
    readonly property int probeLabelCount: _labelCount(graphModel.items)

    function _cardCount(groups) {
        var total = 0
        for (var groupIndex = 0; groupIndex < groups.length; groupIndex++)
            total += groups[groupIndex].cards.length
        return total
    }

    function _labelCount(groups) {
        var total = 0
        for (var groupIndex = 0; groupIndex < groups.length; groupIndex++) {
            var cards = groups[groupIndex].cards
            for (var cardIndex = 0; cardIndex < cards.length; cardIndex++)
                total += cards[cardIndex].labels.length
        }
        return total
    }

    width: 1000
    height: 700
    visible: true
    color: Fluent.Enums.backgroundColor

    CommitTimelineModel {
        id: graphModel
        commits: GraphCommits
    }

    Fluent.Timeline {
        objectName: "commitGraphTimeline"
        anchors.fill: parent
        anchors.margins: Fluent.Enums.spacing.xl
        type: Fluent.Enums.timeline.type_graph
        virtualized: true
        graphLaneCount: graphModel.laneCount
        items: graphModel.items
        selectedRole: "hash"
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


def _run_probe(repo: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.test_git_commit_graph_qml",
            "--render-probe",
            str(repo),
            str(output),
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


def _assert_probe_result(result: subprocess.CompletedProcess[str], output: Path) -> None:
    diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    assert PROBE_MARKER in result.stdout, diagnostic
    assert output.is_file() and output.stat().st_size > 10_000, diagnostic

    from PySide6.QtGui import QImage

    image = QImage(str(output))
    assert not image.isNull(), diagnostic
    assert image.width() >= 900 and image.height() >= 600, diagnostic


def test_real_branched_repo_renders_graph_timeline_in_qml() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-graph-qml-") as temp_dir:
        repo, _hashes = build_branched_repo(Path(temp_dir))
        configured = os.environ.get(SCREENSHOT_ENV, "").strip()
        output = Path(configured) if configured else Path(temp_dir) / "commit-graph.png"
        output.parent.mkdir(parents=True, exist_ok=True)
        _assert_probe_result(_run_probe(repo, output), output)


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _graph_payload(repo: Path) -> list[dict]:
    from app.common.git_service import GitService
    from app_qml.backend.git_bridge import _commit_to_dict

    commits = GitService().get_graph_log_at(str(repo), count=20)
    assert len(commits) == 5
    assert any(len(commit.parents) == 2 for commit in commits)
    assert any(ref.kind == "tag" for commit in commits for ref in commit.refs)
    return [_commit_to_dict(commit) for commit in commits]


def _create_scene(engine, payload: list[dict]):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    engine.rootContext().setContextProperty("GraphCommits", payload)
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "GraphProbe.qml"))
    component.setData(PROBE_SOURCE, base_url)
    for _ in range(50):
        if component.status() != QQmlComponent.Status.Loading:
            break
        _pump(20)
    errors = [error.toString() for error in component.errors()]
    assert component.status() == QQmlComponent.Status.Ready, errors
    root = component.create(engine.rootContext())
    assert root is not None, errors
    return component, root


def _sample_color_count(image) -> int:
    step_x = max(1, image.width() // 50)
    step_y = max(1, image.height() // 35)
    return len(
        {
            image.pixelColor(x, y).rgba()
            for x in range(0, image.width(), step_x)
            for y in range(0, image.height(), step_y)
        }
    )


def _visual_items(root):
    stack = [root.contentItem()]
    while stack:
        item = stack.pop()
        yield item
        stack.extend(reversed(item.childItems()))


def _validate_rendered_scene(root, payload: list[dict], output: Path) -> str:
    from PySide6.QtCore import QObject

    timeline = root.findChild(QObject, "commitGraphTimeline")
    layers = [
        item for item in _visual_items(root)
        if item.objectName() == "timelineGraphLayer"
    ]
    lane_count = int(root.property("probeLaneCount"))
    card_count = int(root.property("probeCardCount"))
    label_count = int(root.property("probeLabelCount"))
    assert timeline is not None and int(timeline.property("graphLaneCount")) == lane_count
    assert lane_count >= 2 and card_count == len(payload) and label_count >= 4
    assert len(layers) >= card_count
    image = root.grabWindow()
    assert not image.isNull() and _sample_color_count(image) >= 4
    assert image.save(str(output), "PNG")
    return (
        f"lanes={lane_count} cards={card_count} labels={label_count} "
        f"layers={len(layers)} colors={_sample_color_count(image)}"
    )


def _render_probe(repo: Path, output: Path) -> int:
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    payload = _graph_payload(repo)
    component, root = _create_scene(engine, payload)
    _pump(600)
    details = _validate_rendered_scene(root, payload, output)
    print(f"{PROBE_MARKER} {details} output={output}")
    root.close()
    root.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--render-probe":
        raise SystemExit("usage: test_git_commit_graph_qml.py --render-probe REPO OUTPUT")
    raise SystemExit(_render_probe(Path(sys.argv[2]), Path(sys.argv[3])))
