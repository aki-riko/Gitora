# coding: utf-8
"""高级页轮询不得重建未变化的工作树按钮。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.git_test_utils import commit_all, init_repo, run_git, write_file


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[ADVANCED_WORKTREE_REFRESH_QML_PROBE]"


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


def test_unchanged_worktree_refresh_preserves_remove_button_instance() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-advanced-refresh-") as temp_dir:
        temp_root = Path(temp_dir)
        repo = init_repo(temp_root / "repo")
        write_file(repo, "tracked.txt", "base\n")
        commit_all(repo, "base")
        worktree = temp_root / "detached"
        run_git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_advanced_worktree_refresh_qml",
                "--probe",
                str(repo),
                str(worktree),
            ],
            cwd=str(ROOT),
            env=_probe_environment(temp_root / "config"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert f"{PROBE_MARKER} preserved=true" in result.stdout, diagnostic


def _to_variant(value):
    converter = getattr(value, "toVariant", None)
    return converter() if callable(converter) else value


def _run_probe(repo: Path, worktree: Path) -> int:
    from PySide6.QtCore import QObject, QTimer
    from shiboken6 import getCppPointer, isValid

    from app_qml.backend import repo_scanner
    from app_qml import main_qml

    repo_scanner.RepoScanner.start = lambda self: None  # type: ignore[method-assign]

    def schedule_probe(app, engine, _ai_commit_bridge) -> None:
        root = engine.rootObjects()[0]
        bridge = engine.rootContext().contextProperty("GitBridge")
        state: dict[str, object] = {
            "button": None,
            "pointer": 0,
            "opened": False,
            "menu": None,
            "phase": "wait_button",
            "finished": False,
        }

        def live_window():
            window = root.property("windowInstance")
            return window if window is not None and isValid(window) else None

        def stack_item(index: int):
            window = live_window()
            stack = window.property("stackedWidget") if window is not None else None
            if stack is None:
                return None
            loaders = _to_variant(stack.property("_loaders")) or []
            if index >= len(loaders) or loaders[index] is None:
                return None
            return loaders[index].property("item")

        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        def detached_button():
            advanced = stack_item(6)
            if advanced is None:
                return None
            for button in visual_items(advanced):
                if button.objectName() != "worktreeRemoveButton":
                    continue
                if Path(str(button.property("worktreePath"))) == worktree:
                    return button
            return None

        def button_menu(button):
            if button is None:
                return None
            for child in button.findChildren(QObject):
                if bool(child.property("_isPopupWindowCore")):
                    return child
            return None

        def fail(message: str) -> None:
            if state["finished"]:
                return
            state["finished"] = True
            window = live_window()
            stack = window.property("stackedWidget") if window is not None else None
            loaders = _to_variant(stack.property("_loaders")) if stack is not None else []
            advanced = stack_item(6)
            buttons = (
                [
                    str(button.property("worktreePath"))
                    for button in visual_items(advanced)
                    if button.objectName() == "worktreeRemoveButton"
                ]
                if advanced is not None
                else []
            )
            print(
                f"{PROBE_MARKER} FAILED {message} "
                f"windowIndex={window.property('currentIndex') if window else None} "
                f"displayIndex={stack.property('_displayIndex') if stack else None} "
                f"loaders={len(loaders or [])} advanced={advanced is not None} "
                f"buttons={buttons}"
            )
            app.exit(2)

        def poll() -> None:
            window = live_window()
            if window is None or window.property("stackedWidget") is None:
                QTimer.singleShot(20, poll)
                return
            if not state["opened"]:
                if not bridge.setRepoPath(str(repo)):
                    fail("cannot open repository")
                    return
                state["opened"] = True
                window.setProperty("currentIndex", 6)
                QTimer.singleShot(20, poll)
                return

            button = detached_button()
            if state["phase"] == "wait_button":
                if button is None:
                    QTimer.singleShot(20, poll)
                    return
                advanced = stack_item(6)
                scroll_area = advanced.findChild(QObject, "advancedScrollArea")
                if scroll_area is None:
                    fail("advanced scroll area missing")
                    return
                flickable = scroll_area.property("flickableItem")
                if flickable is None or not isValid(flickable):
                    fail("advanced flickable missing")
                    return
                from PySide6.QtCore import QPointF

                origin_y = float(flickable.property("originY") or 0)
                content_height = float(flickable.property("contentHeight") or 0)
                viewport_height = float(flickable.property("height") or 0)
                bottom_y = origin_y + max(0, content_height - viewport_height)
                current_y = float(flickable.property("contentY") or origin_y)
                button_center = button.mapToScene(
                    QPointF(button.width() / 2, button.height() / 2)
                )
                target_scene_y = live_window().height() * 0.65
                target_content_y = max(
                    origin_y,
                    min(bottom_y, current_y + button_center.y() - target_scene_y),
                )
                if not flickable.setProperty("contentY", target_content_y):
                    fail("cannot position advanced scroll area")
                    return
                state["button"] = button
                state["pointer"] = getCppPointer(button)[0]
                state["phase"] = "click_button"
                QTimer.singleShot(50, poll)
                return

            if state["phase"] == "click_button":
                from PySide6.QtCore import QPointF, Qt
                from PySide6.QtTest import QTest

                point = button.mapToScene(
                    QPointF(button.width() - 16, button.height() / 2)
                ).toPoint()
                window = live_window()
                if window is None or not (
                    0 <= point.x() < window.width()
                    and 0 <= point.y() < window.height()
                ):
                    fail(
                        f"button is outside window at {point.x()},{point.y()} "
                        f"for {window.width() if window else 0}x"
                        f"{window.height() if window else 0}"
                    )
                    return
                QTest.mouseClick(
                    window,
                    Qt.MouseButton.LeftButton,
                    Qt.KeyboardModifier.NoModifier,
                    point,
                )
                state["phase"] = "wait_menu"
                QTimer.singleShot(20, poll)
                return

            if state["phase"] == "wait_menu":
                menu = button_menu(state["button"])
                if menu is None or not bool(menu.property("isOpen")):
                    QTimer.singleShot(20, poll)
                    return
                state["menu"] = menu
                state["phase"] = "verify"
                QTimer.singleShot(2500, poll)
                return

            original = state["button"]
            if not isValid(original):
                fail("original button was destroyed")
                return
            if button is None:
                fail("refreshed button missing")
                return
            pointer = getCppPointer(button)[0]
            if pointer != state["pointer"]:
                fail(f"button replaced {state['pointer']} -> {pointer}")
                return
            menu = state["menu"]
            if menu is None or not isValid(menu) or not bool(menu.property("isOpen")):
                fail("menu closed during unchanged refresh")
                return
            state["finished"] = True
            print(f"{PROBE_MARKER} preserved=true menuOpen=true pointer={pointer}")
            app.exit(0)

        QTimer.singleShot(0, poll)
        QTimer.singleShot(10000, lambda: fail("timeout"))

    main_qml._schedule_selftest = schedule_probe
    return main_qml.main()


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--probe":
        raise SystemExit(
            "usage: test_advanced_worktree_refresh_qml.py --probe REPO WORKTREE"
        )
    raise SystemExit(_run_probe(Path(sys.argv[2]), Path(sys.argv[3])))
