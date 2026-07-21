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
        self.assertIn("AiCommitPlanBridge(", source)
        self.assertIn('setContextProperty("AiCommitPlanBridge", ai_commit_plan_bridge)', source)
        self.assertIn("statusChanged.connect(ai_commit_plan_bridge.invalidateWorkspace)", source)

    def test_repo_view_uses_two_step_consent_and_does_not_auto_commit(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("AiCommitBridge.prepareCommitMessage()", source)
        self.assertIn("AiCommitBridge.generatePrepared(requestId, false)", source)
        self.assertIn("确认发送差异到远程模型", source)
        self.assertIn("AiCommitBridge.generatePrepared(root._aiPreparedRequestId, true)", source)
        self.assertIn("AiCommitBridge.cancelCurrent()", source)
        self.assertIn("aiCommitPlanDialog.openPlanner()", source)
        self.assertIn("AiCommitPlanBridge.notifyCommitSucceeded()", source)
        self.assertIn("!AiCommitPlanBridge.awaitingCommit", source)
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
        self.assertIn("文件级规划：仅已暂存差异", source)
        self.assertIn("文件级规划：全部工作区改动", source)
        self.assertIn("仅发送到你配置的服务地址", source)
        self.assertNotIn("api_key\"", source)

    def test_plan_dialog_allows_editing_without_git_execution(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitPlanDialog.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("AiCommitPlanBridge.preparePlan()", source)
        self.assertIn("AiCommitPlanBridge.prepareHunkPlan()", source)
        self.assertIn("planModel.moveChange", source)
        self.assertIn("planModel.moveGroup", source)
        self.assertIn("planModel.updateGroupMessage", source)
        self.assertIn("planModel.getGroupPatch", source)
        self.assertIn("AiCommitPlanBridge.applyNextGroup()", source)
        self.assertIn("确认发送工作区差异到远程模型", source)
        self.assertIn("模型提示：", source)
        self.assertIn("代码块覆盖：", source)
        self.assertIn('change.kind === "hunk"', source)
        self.assertIn("change.content", source)
        self.assertIn('change.staged ? "已暂存" : "未暂存"', source)
        self.assertIn("!AiCommitPlanBridge.awaitingCommit", source)
        self.assertNotIn("GitBridge.commit", source)
        self.assertNotIn("GitBridge.push", source)
        self.assertNotIn("GitBridge.stage", source)


if __name__ == "__main__":
    unittest.main()
