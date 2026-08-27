"""QML 入口不得直接调用有阻塞的仓库文件读取。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_advanced_view_uses_async_rule_file_apis() -> None:
    source = (ROOT / "app_qml" / "qml" / "views" / "AdvancedView.qml").read_text(
        encoding="utf-8"
    )

    assert "GitBridge.requestRepoRuleFile(\".gitignore\")" in source
    assert "GitBridge.requestRepoRuleFile(\".gitattributes\")" in source
    assert "GitBridge.saveRepoRuleFileAsync" in source
    assert "GitBridge.readRepoRuleFile(" not in source
    assert "GitBridge.saveRepoRuleFile(" not in source


def test_conflict_viewer_and_clean_preview_use_bounded_async_payloads() -> None:
    conflict = (
        ROOT / "app_qml" / "qml" / "components" / "ConflictViewerDialog.qml"
    ).read_text(encoding="utf-8")
    clean = (
        ROOT / "app_qml" / "qml" / "components" / "CleanDialog.qml"
    ).read_text(encoding="utf-8")

    assert "GitBridge.requestConflictFile(path)" in conflict
    assert "property var lineRows: []" in conflict
    assert "model: dlg.lineRows" in conflict
    assert "GitBridge.readConflictFile(" not in conflict
    assert "function onCleanPreviewReady(repoPath, files, total, isTruncated)" in clean
    assert "dlg.truncated" in clean


def test_repo_scanner_has_result_and_progress_bounds() -> None:
    source = (ROOT / "app_qml" / "backend" / "repo_scanner.py").read_text(
        encoding="utf-8"
    )

    assert "_MAX_SCANNED_REPOSITORIES = 5000" in source
    assert "_PROGRESS_EVERY_DIRECTORIES = 100" in source
    assert "if count >= _MAX_SCANNED_REPOSITORIES" in source

    cache_source = (ROOT / "app" / "common" / "scanned_repos.py").read_text(
        encoding="utf-8"
    )
    assert "MAX_SCANNED_REPOSITORIES = 5000" in cache_source
    assert "if len(self._repos) >= MAX_SCANNED_REPOSITORIES" in cache_source
