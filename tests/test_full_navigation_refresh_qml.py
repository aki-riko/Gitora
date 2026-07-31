# coding: utf-8
"""完整 PrismQML 主导航中的分支与历史刷新回归测试。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import build_branched_repo, run_git


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[FULL_NAVIGATION_REFRESH_QML_PROBE]"


def _extend_branch(repo: Path, branch: str, count: int, prefix: str) -> list[str]:
    parent = run_git(repo, "rev-parse", branch).stdout.strip()
    tree = run_git(repo, "rev-parse", f"{parent}^{{tree}}").stdout.strip()
    commits = []
    for index in range(count):
        parent = run_git(
            repo,
            "commit-tree",
            tree,
            "-p",
            parent,
            "-m",
            f"{prefix} {index}",
        ).stdout.strip()
        commits.append(parent)
    run_git(repo, "update-ref", f"refs/heads/{branch}", parent)
    return commits


def _probe_environment(config_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "GITESS_QML_SELFTEST": "1",
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
            "LOCALAPPDATA": str(config_root),
            "XDG_CONFIG_HOME": str(config_root),
        }
    )
    return environment


def test_full_navigation_refreshes_after_real_git_operations() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-full-nav-refresh-") as temp_dir:
        temp_root = Path(temp_dir)
        repo, _hashes = build_branched_repo(temp_root)
        _extend_branch(repo, "master", 27, "master extra")
        side_commits = _extend_branch(repo, "side", 29, "side extra")
        earlier_commit = side_commits[-6]
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_full_navigation_refresh_qml",
                "--probe",
                str(repo),
                "side",
                earlier_commit,
            ],
            cwd=str(ROOT),
            env=_probe_environment(temp_root / "config"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert f"{PROBE_MARKER} branches=master,side,HEAD" in result.stdout, diagnostic


def _to_variant(value):
    converter = getattr(value, "toVariant", None)
    return converter() if callable(converter) else value


def _run_probe(repo: Path, target_branch: str, checkout_commit: str) -> int:
    from PySide6.QtCore import QTimer

    from app_qml.backend import repo_scanner
    from app_qml import main_qml

    initial_branch = run_git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    initial_top = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    target_top = run_git(repo, "rev-parse", target_branch).stdout.strip()
    checkout_top = run_git(repo, "rev-parse", checkout_commit).stdout.strip()
    initial_message = run_git(repo, "log", "-1", "--format=%s", initial_top).stdout.strip()
    target_message = run_git(repo, "log", "-1", "--format=%s", target_top).stdout.strip()
    checkout_message = run_git(repo, "log", "-1", "--format=%s", checkout_top).stdout.strip()
    initial_count = min(30, int(run_git(repo, "rev-list", "--count", initial_top).stdout))
    target_count = min(30, int(run_git(repo, "rev-list", "--count", target_top).stdout))
    checkout_count = min(30, int(run_git(repo, "rev-list", "--count", checkout_top).stdout))

    repo_scanner.RepoScanner.start = lambda self: None  # type: ignore[method-assign]

    def schedule_probe(app, engine, _ai_commit_bridge) -> None:
        root = engine.rootObjects()[0]
        window = root.property("windowInstance")
        bridge = engine.rootContext().contextProperty("GitBridge")
        state = {
            "phase": "open_history",
            "history": None,
            "branch": None,
            "deadline": 0,
        }

        from time import monotonic

        state["deadline"] = monotonic() + 15

        def fail(message: str) -> None:
            print(f"{PROBE_MARKER} FAILED {message}")
            app.exit(2)

        def stack_and_item(index: int):
            stack = window.property("stackedWidget") if window is not None else None
            if stack is None:
                return None, None
            loaders = _to_variant(stack.property("_loaders")) or []
            if index >= len(loaders) or loaders[index] is None:
                return stack, None
            return stack, loaders[index].property("item")

        def commit_count(history) -> int:
            commits = _to_variant(history.property("allCommits")) or []
            return len(commits)

        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        def branch_button_states(branch_view) -> dict[str, str]:
            if branch_view is None:
                return {}
            return {
                str(item.property("branchName")): str(item.property("text"))
                for item in visual_items(branch_view)
                if item.objectName() == "localBranchActionButton"
            }

        def timeline_texts(history) -> set[str]:
            timeline = history.findChild(type(history), "historyTimeline")
            if timeline is None:
                from PySide6.QtCore import QObject

                timeline = history.findChild(QObject, "historyTimeline")
            if timeline is None:
                return set()
            texts = set()
            for item in visual_items(timeline):
                value = item.property("text")
                if value:
                    texts.add(str(value))
            return texts

        def find_visual(root_item, predicate):
            for item in visual_items(root_item):
                if predicate(item):
                    return item
            return None

        def click_item(item) -> None:
            from PySide6.QtCore import QPointF, Qt
            from PySide6.QtTest import QTest

            point = item.mapToScene(
                QPointF(item.width() / 2, item.height() / 2)
            ).toPoint()
            QTest.mouseClick(
                window,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                point,
            )

        def hover_branch_row(branch_view, branch_name: str) -> None:
            from PySide6.QtCore import QPointF
            from PySide6.QtTest import QTest

            row = find_visual(
                branch_view,
                lambda item: item.objectName() == "branchRowDelegate"
                and item.property("branchName") == branch_name,
            )
            if row is None:
                return
            point = row.mapToScene(
                QPointF(row.width() - 20, row.height() / 2)
            ).toPoint()
            QTest.mouseMove(window, point)

        def poll() -> None:
            if monotonic() >= state["deadline"]:
                history = state["history"]
                branch_view = state["branch"]
                stack = window.property("stackedWidget") if window is not None else None
                _stack, live_branch_view = stack_and_item(2)
                fail(
                    f"timeout phase={state['phase']} "
                    f"historyBranch={history.property('currentBranch') if history else None} "
                    f"historyCount={commit_count(history) if history else None} "
                    f"branchView={branch_view.property('currentBranch') if branch_view else None} "
                    f"branchButtons={branch_button_states(branch_view)} "
                    f"liveBranch={live_branch_view.property('currentBranch') if live_branch_view else None} "
                    f"liveButtons={branch_button_states(live_branch_view)} "
                    f"sameBranchPage={live_branch_view is branch_view} "
                    f"displayIndex={stack.property('_displayIndex') if stack else None} "
                    f"windowIndex={window.property('currentIndex') if window else None}"
                )
                return

            phase = state["phase"]
            stack = window.property("stackedWidget") if window is not None else None
            if stack is None:
                QTimer.singleShot(20, poll)
                return

            if phase == "open_history":
                if not bridge.setRepoPath(str(repo)):
                    fail("cannot open repository")
                    return
                window.setProperty("currentIndex", 1)
                state["phase"] = "wait_master"
            elif phase == "wait_master":
                stack, history = stack_and_item(1)
                if (
                    history is not None
                    and stack.property("_displayIndex") == 1
                    and history.property("currentBranch") == initial_branch
                    and commit_count(history) == initial_count
                    and initial_message in timeline_texts(history)
                    and initial_branch in timeline_texts(history)
                ):
                    state["history"] = history
                    window.setProperty("currentIndex", 2)
                    state["phase"] = "click_side_branch"
            elif phase == "click_side_branch":
                stack, branch_view = stack_and_item(2)
                if (
                    branch_view is not None
                    and stack.property("_displayIndex") == 2
                    and branch_view.property("currentBranch") == initial_branch
                ):
                    hover_branch_row(branch_view, target_branch)
                    button = find_visual(
                        branch_view,
                        lambda item: item.objectName() == "localBranchActionButton"
                        and item.property("branchName") == target_branch,
                    )
                    if button is not None:
                        state["branch"] = branch_view
                        click_item(button)
                        state["phase"] = "wait_branch_page"
            elif phase == "wait_branch_page":
                stack, branch_view = stack_and_item(2)
                if branch_view is not None:
                    hover_branch_row(branch_view, target_branch)
                current_button = (
                    find_visual(
                        branch_view,
                        lambda item: item.objectName() == "localBranchActionButton"
                        and item.property("branchName") == target_branch,
                    )
                    if branch_view is not None
                    else None
                )
                if (
                    branch_view is not None
                    and stack.property("_displayIndex") == 2
                    and branch_view.property("currentBranch") == target_branch
                    and current_button is not None
                    and current_button.property("text") == "管理"
                ):
                    state["branch"] = branch_view
                    window.setProperty("currentIndex", 1)
                    state["phase"] = "return_history"
            elif phase == "return_history":
                stack, history = stack_and_item(1)
                if (
                    history is not None
                    and stack.property("_displayIndex") == 1
                    and history.property("currentBranch") == target_branch
                    and commit_count(history) == target_count
                    and target_message in timeline_texts(history)
                    and target_branch in timeline_texts(history)
                ):
                    state["history"] = history
                    commits = _to_variant(history.property("allCommits")) or []
                    selected = next(
                        (
                            commit
                            for commit in commits
                            if commit.get("hash") == checkout_top
                        ),
                        None,
                    )
                    button = find_visual(
                        history,
                        lambda item: item.property("text") == "检出提交",
                    )
                    if selected is not None and button is not None:
                        history.setProperty("selectedCommit", selected)
                        click_item(button)
                        state["phase"] = "wait_detached"
            elif phase == "wait_detached":
                history = state["history"]
                if (
                    history.property("currentBranch") == "HEAD"
                    and commit_count(history) == checkout_count
                    and checkout_message in timeline_texts(history)
                    and "HEAD" in timeline_texts(history)
                ):
                    print(
                        f"{PROBE_MARKER} branches={initial_branch},"
                        f"{target_branch},HEAD tops={initial_top[:8]},"
                        f"{target_top[:8]},{checkout_top[:8]} "
                        f"branch={state['branch'].property('currentBranch')}"
                    )
                    app.exit(0)
                    return
            QTimer.singleShot(20, poll)

        QTimer.singleShot(0, poll)

    main_qml._schedule_selftest = schedule_probe
    return main_qml.main()


if __name__ == "__main__":
    if len(sys.argv) != 5 or sys.argv[1] != "--probe":
        raise SystemExit(
            "usage: test_full_navigation_refresh_qml.py --probe REPO BRANCH COMMIT"
        )
    raise SystemExit(_run_probe(Path(sys.argv[2]), sys.argv[3], sys.argv[4]))
