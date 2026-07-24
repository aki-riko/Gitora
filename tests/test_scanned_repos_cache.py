# coding: utf-8
from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from app.common.scanned_repos import ScannedReposCache
from app_qml.backend.repo_scanner import RepoScanner


def _wait_until(predicate, timeout_ms: int = 10_000) -> bool:
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: predicate() and loop.quit())
    QTimer.singleShot(timeout_ms, loop.quit)
    timer.start()
    loop.exec()
    timer.stop()
    return bool(predicate())


def _make_repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def test_scanned_repo_cache_persists_deduplicates_and_prunes(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "repo")
    cache_path = tmp_path / "scanned_repos.json"
    cache = ScannedReposCache(cache_path)

    alternate_path = (
        repo.as_posix()
        if os.name == "nt"
        else f"{repo.parent}{os.sep}.{os.sep}{repo.name}"
    )
    cache.add(str(repo))
    cache.add(alternate_path)
    cache.save()

    reloaded = ScannedReposCache(cache_path)
    assert reloaded.get_all() == [os.path.normpath(str(repo))]
    assert json.loads(cache_path.read_text(encoding="utf-8"))["repos"] == [
        os.path.normpath(str(repo))
    ]

    (repo / ".git").rmdir()
    assert reloaded.get_all() == []
    assert json.loads(cache_path.read_text(encoding="utf-8"))["repos"] == []


def test_repo_scanner_restores_previous_results_after_restart(tmp_path: Path) -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    cache_path = tmp_path / "scanned_repos.json"
    first = _make_repo(tmp_path / "first")
    second = _make_repo(tmp_path / "group" / "second")
    scanner = RepoScanner(cache=ScannedReposCache(cache_path))
    finished: list[int] = []
    scanner.scanFinished.connect(finished.append)

    try:
        scanner.start([str(tmp_path)])
        assert _wait_until(lambda: finished == [2])
        assert sorted(scanner.getResults()) == sorted((str(first), str(second)))
    finally:
        scanner.shutdown()
        scanner.deleteLater()
        app.processEvents()

    restored = RepoScanner(cache=ScannedReposCache(cache_path))
    try:
        assert sorted(restored.getResults()) == sorted((str(first), str(second)))
    finally:
        restored.shutdown()
        restored.deleteLater()
        app.processEvents()


def test_cancelled_scan_count_excludes_cached_results(tmp_path: Path) -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    cache_path = tmp_path / "scanned_repos.json"
    cached = _make_repo(tmp_path / "cached")
    discovered = _make_repo(tmp_path / "discovered")
    cache = ScannedReposCache(cache_path)
    cache.add(str(cached))
    cache.save()
    scanner = RepoScanner(cache=ScannedReposCache(cache_path))
    finished: list[int] = []
    scanner.scanFinished.connect(finished.append)

    try:
        scanner._on_repo_found(str(discovered))
        scanner._finish_without_result()
        assert finished == [1]
        assert sorted(scanner.getResults()) == sorted((str(cached), str(discovered)))
    finally:
        scanner.shutdown()
        scanner.deleteLater()
        app.processEvents()
