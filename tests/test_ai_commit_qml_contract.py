# coding: utf-8
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AiCommitQmlContractTest(unittest.TestCase):
    def test_main_registers_shared_ai_bridge(self) -> None:
        source = (ROOT / "app_qml" / "main_qml.py").read_text(encoding="utf-8")
        self.assertIn("AiCommitBridge(git_bridge.service)", source)
        self.assertIn('setContextProperty("AiCommitBridge", ai_commit_bridge)', source)
        self.assertIn("repoPathChanged.connect(ai_commit_bridge.invalidateRepo)", source)
        self.assertIn("statusChanged.connect(ai_commit_bridge.invalidateWorkspace)", source)

    def test_repo_view_uses_two_step_consent_and_does_not_auto_commit(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("AiCommitBridge.prepareCommitMessage()", source)
        self.assertIn("AiCommitBridge.generatePrepared(requestId, false)", source)
        self.assertIn("确认发送差异到远程模型", source)
        self.assertIn("AiCommitBridge.generatePrepared(root._aiPreparedRequestId, true)", source)
        self.assertIn("AiCommitBridge.cancelCurrent()", source)
        self.assertIn("Fluent.TextEdit {\n                id: commitInput", source)
        ai_handler = source.split("function onCommitMessageReady", 1)[1].split("function onErrorOccurred", 1)[0]
        self.assertNotIn("GitBridge.commit", ai_handler)
        self.assertNotIn("GitBridge.push", ai_handler)

    def test_settings_card_keeps_secret_session_only(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitSettingsCard.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("input.type_password", source)
        self.assertIn("AiCommitBridge.setSessionApiKey", source)
        self.assertIn("仅保留到退出", source)
        self.assertIn("当前生成范围：仅已暂存差异", source)
        self.assertIn("仅发送到你配置的服务地址", source)
        self.assertNotIn("全部工作区差异", source)
        self.assertNotIn("api_key\"", source)


if __name__ == "__main__":
    unittest.main()
