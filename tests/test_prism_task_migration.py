# coding: utf-8
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, QTimer

from app.common.scanned_repos import ScannedReposCache
from app_qml.backend.git_bridge import GitBridge
from app_qml.backend.repo_scanner import RepoScanner


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOTS = (ROOT / "app", ROOT / "app_qml")


def _production_python_files() -> list[Path]:
    return [
        path
        for root in PRODUCTION_ROOTS
        for path in root.rglob("*.py")
    ]


def _wait_until(app: QCoreApplication, predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    app.processEvents()
    return bool(predicate())


def test_production_code_has_no_hand_written_thread_workers() -> None:
    violations: list[str] = []
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = {
                    alias.name
                    for alias in node.names
                }
                if "QThread" in imported:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: QThread import")
            if isinstance(node, ast.Call):
                function = node.func
                if (
                    isinstance(function, ast.Attribute)
                    and isinstance(function.value, ast.Name)
                    and function.value.id == "threading"
                    and function.attr == "Thread"
                ):
                    violations.append(
                        f"{path.relative_to(ROOT)}:{node.lineno}: threading.Thread"
                    )
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "QThread":
                        violations.append(
                            f"{path.relative_to(ROOT)}:{node.lineno}: QThread subclass"
                        )
    assert violations == []


def test_git_service_slots_do_not_return_synchronous_results_to_qml() -> None:
    path = ROOT / "app_qml" / "backend" / "git_bridge.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    bridge = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GitBridge"
    )
    for function in bridge.body:
        if not isinstance(function, ast.FunctionDef):
            continue
        slot_decorators = [
            decorator
            for decorator in function.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "Slot"
        ]
        if not slot_decorators:
            continue
        calls_git_service = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
            and node.func.value.attr == "_svc"
            for node in ast.walk(function)
        )
        if not calls_git_service:
            continue
        for decorator in slot_decorators:
            result = next(
                (
                    keyword.value
                    for keyword in decorator.keywords
                    if keyword.arg == "result"
                ),
                None,
            )
            if result is None:
                continue
            if not (isinstance(result, ast.Name) and result.id == "QObject"):
                violations.append(
                    f"{function.name}:{function.lineno} exposes a synchronous result"
                )
    assert violations == []


def test_cherry_pick_submission_returns_before_slow_git_finishes() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    bridge = GitBridge()
    bridge._poll_timer.stop()
    started = threading.Event()
    release = threading.Event()
    heartbeat: list[bool] = []
    results: list[object] = []
    callback_threads: list[QThread] = []

    def slow_cherry_pick(commit_hash: str, target_branch: str):
        assert commit_hash == "abc123"
        assert target_branch == "target"
        started.set()
        release.wait(5)
        return True, "done"

    bridge._svc.cherry_pick_to_branch = slow_cherry_pick  # type: ignore[method-assign]
    try:
        before = time.monotonic()
        handle = bridge.cherryPickToBranch("abc123", "target")
        elapsed = time.monotonic() - before
        handle.succeeded.connect(results.append)
        handle.succeeded.connect(
            lambda _result: callback_threads.append(QThread.currentThread())
        )
        QTimer.singleShot(0, lambda: heartbeat.append(True))

        assert elapsed < 0.1
        assert started.wait(5)
        assert _wait_until(app, lambda: heartbeat == [True])
        assert results == []

        release.set()
        assert _wait_until(app, lambda: results == [(True, "done")])
        assert callback_threads == [app.thread()]
    finally:
        release.set()
        bridge.deleteLater()
        app.processEvents()


def test_repo_scanner_uses_engine_task_and_reports_on_main_thread(
    tmp_path: Path,
) -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    first = tmp_path / "first"
    second = tmp_path / "group" / "second"
    (first / ".git").mkdir(parents=True)
    (second / ".git").mkdir(parents=True)
    scanner = RepoScanner(
        cache=ScannedReposCache(tmp_path / "scanned_repos.json")
    )
    found: list[str] = []
    finished: list[int] = []
    callback_threads: list[QThread] = []
    scanner.repoFound.connect(found.append)
    scanner.scanFinished.connect(finished.append)
    scanner.scanFinished.connect(
        lambda _count: callback_threads.append(QThread.currentThread())
    )

    try:
        scanner.start([str(tmp_path)])
        assert scanner.scanning
        assert _wait_until(app, lambda: finished == [2])
        assert sorted(found) == sorted((str(first), str(second)))
        assert callback_threads == [app.thread()]
        assert not scanner.scanning
    finally:
        scanner.shutdown()
        scanner.deleteLater()
        app.processEvents()
