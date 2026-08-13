# coding: utf-8
"""工作树分离按钮与强制删除确认的 QML 契约测试。"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADVANCED_VIEW = ROOT / "app_qml" / "qml" / "views" / "AdvancedView.qml"


def test_detached_worktree_uses_transparent_split_remove_button() -> None:
    source = ADVANCED_VIEW.read_text(encoding="utf-8")

    assert "style: Fluent.Enums.button.style_transparent" in source
    assert "feature: model.detached" in source
    assert "Fluent.Enums.button.feature_split" in source
    assert '{ "text": "强制删除", "icon": Fluent.Enums.icon.warning }' in source
    assert "forceRemoveWorktreeDanger.start()" in source


def test_force_remove_requires_danger_confirmation_and_force_flag() -> None:
    source = ADVANCED_VIEW.read_text(encoding="utf-8")

    assert 'objectName: "forceRemoveWorktreeDanger"' in source
    assert 'title: "确认强制删除游离工作树"' in source
    assert "countdown: 3" in source
    assert "不会自动创建提交、stash 或备份" in source
    assert "GitBridge.removeWorktree(root._pendingWorktreeRemove, true)" in source
    assert "GitBridge.removeWorktree(root._pendingWorktreeRemove, false)" in source
