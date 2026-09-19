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
    # GUI 主线程路径(构造/get_all)不做文件系统探测:条目原样保留,
    # 失效清理由池线程的 prune_missing 负责(网络路径 exists() 会阻塞主线程)。
    assert reloaded.get_all() == [os.path.normpath(str(repo))]
    assert json.loads(cache_path.read_text(encoding="utf-8"))["repos"] == [
        os.path.normpath(str(repo))
    ]

    reloaded.prune_missing()
    assert reloaded.get_all() == []
    assert json.loads(cache_path.read_text(encoding="utf-8"))["repos"] == []


def test_scanned_repo_cache_gui_paths_never_probe_filesystem(
    tmp_path: Path, monkeypatch
) -> None:
    """构造与 get_all 必须零探测:远端断开时 exists() 能阻塞主线程数十秒,
    曾把应用卡死在启动页(2026-09-19 复发记录)。"""
    import app.common.scanned_repos as scanned_module

    cache_path = tmp_path / "scanned_repos.json"
    cache = ScannedReposCache(cache_path)
    cache.add(str(tmp_path / "ghost-repo"))  # 从未创建的本地路径
    if os.name == "nt":
        # UNC 指向 TEST-NET(永不路由),模拟断开的网络共享;条目应原样保留
        cache.add("\\\\192.0.2.1\\share\\repo")
    cache.save()

    real_exists = scanned_module.Path.exists
    probes: list[str] = []

    def spy_exists(path: Path) -> bool:
        probes.append(str(path))
        return real_exists(path)

    monkeypatch.setattr(scanned_module.Path, "exists", spy_exists)

    reloaded = ScannedReposCache(cache_path)
    expected = [os.path.normpath(str(tmp_path / "ghost-repo"))]
    if os.name == "nt":
        expected.append(os.path.normpath("\\\\192.0.2.1\\share\\repo"))
    assert reloaded.get_all() == expected
    # 只允许碰缓存文件本身(_load 的存在性检查),不得探测任何仓库路径
    assert probes == [str(cache_path)]


def test_scan_task_prunes_stale_cache_entries(tmp_path: Path) -> None:
    """失效校验随扫描任务在池线程执行,清理结果回传 GUI 侧结果列表。"""
    app = QCoreApplication.instance() or QCoreApplication([])
    live = _make_repo(tmp_path / "live")
    cache_path = tmp_path / "scanned_repos.json"
    cache = ScannedReposCache(cache_path)
    cache.add(str(tmp_path / "ghost"))  # 从未存在
    cache.add(str(live))
    cache.save()
    scanner = RepoScanner(cache=ScannedReposCache(cache_path))
    finished: list[int] = []
    scanner.scanFinished.connect(finished.append)

    try:
        scanner.start([str(tmp_path)])
        assert _wait_until(lambda: finished == [1])
        assert json.loads(cache_path.read_text(encoding="utf-8"))["repos"] == [
            os.path.normpath(str(live))
        ]
        assert scanner.getResults() == [os.path.normpath(str(live))]
    finally:
        scanner.shutdown()
        scanner.deleteLater()
        app.processEvents()


def test_scanned_repo_cache_ignores_non_object_json_root(tmp_path: Path) -> None:
    cache_path = tmp_path / "scanned_repos.json"
    cache_path.write_text("[]", encoding="utf-8")

    cache = ScannedReposCache(cache_path)

    assert cache.get_all() == []


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


def test_opened_repositories_have_priority_and_deduplicate_equivalent_paths(
    tmp_path: Path,
) -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    overlap_repo = _make_repo(tmp_path / "PriorityRepo")
    opened_only_repo = _make_repo(tmp_path / "OpenedOnly")
    scanned_only_repo = _make_repo(tmp_path / "ScannedOnly")
    cache_path = tmp_path / "scanned_repos.json"
    cache = ScannedReposCache(cache_path)
    cache.add(str(scanned_only_repo))
    cache.add(str(overlap_repo))
    cache.save()
    scanner = RepoScanner(cache=ScannedReposCache(cache_path))
    opened_path = (
        str(overlap_repo).swapcase()
        if os.name == "nt"
        else f"{overlap_repo.parent}{os.sep}.{os.sep}{overlap_repo.name}"
    )

    try:
        assert scanner.mergeWithOpenedRepos(
            [opened_path, str(opened_only_repo)]
        ) == [
            os.path.normpath(opened_path),
            str(opened_only_repo),
            str(scanned_only_repo),
        ]
    finally:
        scanner.shutdown()
        scanner.deleteLater()
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
