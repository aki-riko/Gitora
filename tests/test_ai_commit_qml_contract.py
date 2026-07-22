# coding: utf-8
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AiCommitQmlContractTest(unittest.TestCase):
    @staticmethod
    def _settings_qml_source() -> str:
        components = ROOT / "app_qml" / "qml" / "components"
        return "\n".join(
            (components / name).read_text(encoding="utf-8")
            for name in (
                "AiCommitSettingsCard.qml",
                "AiCommitConnectionSection.qml",
                "AiCommitRulesSection.qml",
            )
        )

    def test_main_registers_shared_ai_bridge(self) -> None:
        source = (ROOT / "app_qml" / "main_qml.py").read_text(encoding="utf-8")
        self.assertIn("AiCommitBridge(git_bridge.service)", source)
        self.assertIn('setContextProperty("AiCommitBridge", ai_commit_bridge)', source)
        self.assertIn("repoPathChanged.connect(ai_commit_bridge.invalidateRepo)", source)
        self.assertIn("statusChanged.connect(ai_commit_bridge.invalidateWorkspace)", source)
        self.assertIn("AiCommitPlanBridge(", source)
        self.assertIn('setContextProperty("AiCommitPlanBridge", ai_commit_plan_bridge)', source)
        self.assertIn("statusChanged.connect(ai_commit_plan_bridge.invalidateWorkspace)", source)
        self.assertIn(
            "settingsChanged.connect(ai_commit_plan_bridge.invalidateSettings)",
            source,
        )
        self.assertIn("GITESS_AI_CONNECTION_SELFTEST", source)
        self.assertIn("GITESS_SETTINGS_NAV_SELFTEST", source)
        self.assertIn("ai_commit_bridge.testConnection", source)

    def test_settings_view_imports_ai_component(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "views" / "SettingsView.qml"
        ).read_text(encoding="utf-8")
        self.assertIn('import "../components"', source)

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
        self.assertIn(
            "AiCommitPlanBridge.busy || AiCommitPlanBridge.awaitingCommit", source
        )
        self.assertIn("CommitComposer {", source)
        self.assertIn("root._setCommitMessage(title, body)", source)
        ai_handler = source.split("function onCommitMessageReady", 1)[1].split("function onErrorOccurred", 1)[0]
        self.assertNotIn("GitBridge.commit", ai_handler)
        self.assertNotIn("GitBridge.push", ai_handler)

    def test_commit_composer_uses_single_line_title_and_optional_body(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "components" / "CommitComposer.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("Fluent.LineEdit {\n                id: commitTitleInput", source)
        self.assertIn("Fluent.TextEdit {\n        id: commitBodyInput", source)
        self.assertIn('placeholderText: "提交标题"', source)
        self.assertIn('placeholderText: "提交正文（可选）"', source)
        self.assertIn('? "编辑正文" : "添加正文"', source)
        self.assertIn("visible: root.bodyExpanded", source)
        self.assertIn("root.bodyExpanded = commitBodyInput.text.trim().length > 0", source)
        self.assertIn('return title + (body.length > 0 ? "\\n\\n" + body : "")', source)

    def test_repo_view_clears_ai_request_and_locks_index_operations(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
        ).read_text(encoding="utf-8")
        repo_change_handler = source.split("function onRepoPathChanged", 1)[1].split(
            "function onStatusReady", 1
        )[0]
        error_handler = source.split("function onErrorOccurred", 1)[1].split("}", 1)[0]
        self.assertIn('root._aiPreparedRequestId = ""', repo_change_handler)
        self.assertIn("remoteAiConfirm.reject()", repo_change_handler)
        self.assertIn('root._aiPreparedRequestId = ""', error_handler)
        self.assertIn("readonly property bool _aiPlanLocksIndex", source)
        self.assertGreaterEqual(source.count("enabled: !root._aiPlanLocksIndex"), 3)
        self.assertIn("&& !root._aiPlanLocksIndex", source)
        self.assertIn(
            "&& (!AiCommitPlanBridge || !AiCommitPlanBridge.busy)", source
        )

    def test_settings_card_uses_system_credential_store_only(self) -> None:
        source = self._settings_qml_source()
        self.assertIn("input.type_password", source)
        self.assertIn("AiCommitBridge.storeApiKey", source)
        self.assertIn("AiCommitBridge.deleteStoredApiKey", source)
        self.assertIn("保存到系统凭据库", source)
        self.assertNotIn("setSessionApiKey", source)
        self.assertNotIn("仅保留到退出", source)
        self.assertIn("提交规划：仅已暂存差异", source)
        self.assertIn("提交规划：全部工作区改动", source)
        self.assertIn("仅本机回环 Ollama 直接发送", source)
        self.assertIn("非本机 Ollama 与远程 API 每次发送前都会确认", source)
        self.assertNotIn("api_key\"", source)

    def test_settings_card_groups_connection_and_generation_rules(self) -> None:
        source = self._settings_qml_source()

        self.assertIn('text: "模型连接"', source)
        self.assertIn('text: "生成规则"', source)
        self.assertIn('text: "模型来源"', source)
        self.assertIn('text: "服务地址"', source)
        self.assertIn('text: "系统凭据"', source)
        self.assertIn('text: "环境变量回退（可选）"', source)
        self.assertIn("Fluent.ToggleSwitch", source)
        self.assertIn("AiCommitConnectionSection", source)
        self.assertIn("AiCommitRulesSection", source)
        self.assertIn("columns: root.compact ? 1 : 3", source)
        self.assertIn("columns: root.compact ? 1 : 2", source)
        self.assertIn("root.width < 760", source)
        self.assertNotIn("connectionPanel", source)
        self.assertNotIn("rulesPanel", source)
        self.assertNotIn("enabledCheck", source)
        self.assertNotIn("bodyCheck", source)

    def test_rules_grid_keeps_both_columns_inside_available_width(self) -> None:
        source = (
            ROOT
            / "app_qml"
            / "qml"
            / "components"
            / "AiCommitRulesSection.qml"
        ).read_text(encoding="utf-8")
        column_constraints = source.split("id: rulesFields", 1)[1].split(
            "id: bodyOptionLayout", 1
        )[0]

        self.assertEqual(column_constraints.count("Layout.minimumWidth: 0"), 2)
        self.assertEqual(column_constraints.count("Layout.preferredWidth: 1"), 2)
        self.assertIn("Layout.columnSpan: rulesFields.columns", source)

    def test_builds_include_native_keyring_dependencies_without_alt(self) -> None:
        windows = (ROOT / "build_nuitka.py").read_text(encoding="utf-8")
        macos = (ROOT / "build_nuitka_mac.py").read_text(encoding="utf-8")
        requirements = (
            ROOT / "app_qml" / "requirements.txt"
        ).read_text(encoding="utf-8")

        self.assertIn('"--include-package=keyring"', windows)
        self.assertIn('"--include-package=win32ctypes"', windows)
        self.assertIn('"--include-package=keyring"', macos)
        self.assertIn("keyring==25.7.0", requirements)
        self.assertNotIn("keyrings.alt", windows + macos + requirements)

    def test_plan_dialog_allows_editing_without_git_execution(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitPlanDialog.qml"
        ).read_text(encoding="utf-8")
        row_source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitChangeRow.qml"
        ).read_text(encoding="utf-8")
        self.assertIn("AiCommitPlanBridge.preparePlan()", source)
        self.assertIn("AiCommitPlanBridge.prepareHunkPlan()", source)
        self.assertIn("planModel.moveChange", source)
        self.assertIn("planModel.moveGroup", source)
        self.assertIn("planModel.updateGroupMessage", source)
        self.assertIn("planModel.getGroupPatch", source)
        self.assertIn("AiCommitPlanBridge.applyNextGroup()", source)
        self.assertNotIn("代码块执行待启用", source)
        self.assertIn("确认发送工作区差异到远程模型", source)
        self.assertIn("模型提示：", source)
        self.assertIn("代码块覆盖：", source)
        self.assertIn("AiCommitChangeRow", source)
        self.assertIn('row.change.kind === "hunk"', row_source)
        self.assertIn("row.change.content", row_source)
        self.assertIn('row.change.staged ? "已暂存" : "未暂存"', row_source)
        self.assertIn("!AiCommitPlanBridge.awaitingCommit", source)
        self.assertNotIn("GitBridge.commit", source)
        self.assertNotIn("GitBridge.push", source)
        self.assertNotIn("GitBridge.stage", source)

    def test_plan_dialog_renders_dynamic_content_as_plain_text(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitPlanDialog.qml"
        ).read_text(encoding="utf-8")
        row_source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitChangeRow.qml"
        ).read_text(encoding="utf-8")
        for qml_source in (source, row_source):
            text_elements = re.findall(r"(?<![A-Za-z])Text\s*\{", qml_source)
            self.assertEqual(
                len(text_elements), qml_source.count("textFormat: Text.PlainText")
            )
        self.assertIn('title: "计划差异预览"', source)
        self.assertNotIn('title: "计划差异：" + dlg._previewTitle', source)
        self.assertIn("text: dlg._previewTitle", source)
        self.assertIn("enabled: !AiCommitPlanBridge || !AiCommitPlanBridge.busy", source)
        self.assertIn("interactionEnabled: AiCommitPlanBridge", source)
        self.assertIn("enabled: interactionEnabled", row_source)

    def test_macos_build_runs_packaged_ai_connection_selftest(self) -> None:
        source = (
            ROOT / ".github" / "workflows" / "build-macos.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("tools/packaged_ai_connection_selftest.py", source)
        self.assertIn("AI 连接检测成功", source)
        self.assertIn("actions/checkout@v7", source)
        self.assertIn("actions/setup-python@v7", source)
        self.assertIn("设置页导航成功", source)
        self.assertEqual(source.count("actions/upload-artifact@v7"), 2)

    def test_cross_platform_selftest_uses_node_24_actions(self) -> None:
        source = (
            ROOT / ".github" / "workflows" / "selftest-crossplatform.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("actions/checkout@v7", source)
        self.assertIn("actions/setup-python@v7", source)
        self.assertIn("GITESS_SETTINGS_NAV_SELFTEST", source)
        self.assertIn("设置页导航成功", source)

    def test_implementation_plan_records_remaining_quality_evaluation(self) -> None:
        source = (
            ROOT / "docs" / "ai-commit-planner-plan.md"
        ).read_text(encoding="utf-8")
        self.assertIn("状态: 已实施（v1.3.0；真实模型质量评测待运行）", source)


if __name__ == "__main__":
    unittest.main()
