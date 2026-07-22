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

    def test_repo_view_uses_single_ai_commit_flow(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
        ).read_text(encoding="utf-8")
        result_source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitResultDialog.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("AiCommitBridge.prepareCommitMessage()", source)
        self.assertIn("AiCommitBridge.generatePrepared(requestId, isRemote)", source)
        self.assertIn("Fluent.ProgressDialog {", source)
        self.assertIn("aiCommitProgress.open()", source)
        self.assertIn("aiCommitProgress.close()", source)
        self.assertIn("AiCommitResultDialog {", source)
        self.assertIn("aiCommitResultDialog.openPlan(title, body, message)", source)
        self.assertIn('"AI 提交方案已失效", "工作区发生变化，请重新生成"', source)
        self.assertIn("aiCommitResultDialog.reject()", source)
        self.assertNotIn("remoteAiConfirm", source)
        self.assertNotIn("AiCommitPlanDialog {", source)
        self.assertIn("CommitComposer {", source)
        self.assertIn("onAiCommitRequested: root._requestAiCommitMessage()", source)
        accepted_handler = source.split("onAccepted:", 1)[1].split("onRejected:", 1)[0]
        self.assertIn("root._submitAiCommit(planTitle, planBody)", accepted_handler)
        submit_handler = source.split("function _submitAiCommit", 1)[1].split(
            "function doAmend", 1
        )[0]
        self.assertIn("root._quickCommitPush(message)", submit_handler)
        self.assertNotIn("GitBridge.commit", submit_handler)
        self.assertNotIn("GitBridge.push", submit_handler)
        self.assertNotIn("_aiCommitScope", source)

        self.assertIn("Fluent.DialogBoxCore {", result_source)
        self.assertEqual(
            result_source.count("style: Fluent.Enums.button.style_filled"), 2
        )
        self.assertIn("level: Fluent.Enums.statusLevel.error", result_source)
        self.assertIn("level: Fluent.Enums.statusLevel.success", result_source)
        self.assertIn('text: "不采用"', result_source)
        self.assertIn('text: "采用并提交推送"', result_source)

    def test_commit_composer_keeps_only_title_and_submit_split_button(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "components" / "CommitComposer.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("Fluent.LineEdit {\n            id: commitTitleInput", source)
        self.assertIn('placeholderText: "提交标题"', source)
        self.assertIn("signal aiCommitRequested()", source)
        self.assertIn('"text": "AI 提交"', source)
        self.assertIn("Fluent.Enums.icon.sparkle", source)
        self.assertIn("feature: Fluent.Enums.button.feature_split", source)
        self.assertIn("onAiCommitRequested", (
            ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("Fluent.TextEdit", source)
        self.assertNotIn("添加正文", source)
        self.assertNotIn("收起正文", source)
        self.assertNotIn("AI 生成", source)
        self.assertNotIn("规划提交", source)
        self.assertNotIn("signal aiRequested()", source)
        self.assertNotIn("signal planRequested()", source)

    def test_repo_view_clears_ai_request_and_locks_index_operations(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
        ).read_text(encoding="utf-8")
        repo_change_handler = source.split("function onRepoPathChanged", 1)[1].split(
            "function onStatusReady", 1
        )[0]
        error_handler = source.split("function onErrorOccurred", 1)[1].split("}", 1)[0]
        self.assertIn('root._aiPreparedRequestId = ""', repo_change_handler)
        self.assertIn("aiCommitProgress.close()", repo_change_handler)
        self.assertIn("aiCommitResultDialog.reject()", repo_change_handler)
        self.assertIn('root._aiPreparedRequestId = ""', error_handler)
        self.assertNotIn("readonly property bool _aiPlanLocksIndex", source)

    def test_ai_bridge_errors_have_single_global_notification_owner(self) -> None:
        repo_source = (
            ROOT / "app_qml" / "qml" / "views" / "RepoView.qml"
        ).read_text(encoding="utf-8")
        settings_source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitSettingsCard.qml"
        ).read_text(encoding="utf-8")
        host_source = (
            ROOT / "app_qml" / "qml" / "components" / "ToastProgressHost.qml"
        ).read_text(encoding="utf-8")

        repo_error_handler = repo_source.split(
            "function onErrorOccurred", 1
        )[1].split("}", 1)[0]
        self.assertNotIn("NotificationManager", repo_error_handler)
        self.assertNotIn("function onErrorOccurred", settings_source)
        self.assertEqual(host_source.count("function onErrorOccurred"), 1)
        self.assertIn(
            'Fluent.NotificationManager.desktop.error("AI 提交规划", message)',
            host_source,
        )

    def test_settings_card_uses_system_credential_store_only(self) -> None:
        source = self._settings_qml_source()
        self.assertIn("input.type_password", source)
        self.assertIn("AiCommitBridge.storeApiKey", source)
        self.assertIn("AiCommitBridge.deleteStoredApiKey", source)
        self.assertIn("保存到系统凭据库", source)
        self.assertNotIn("setSessionApiKey", source)
        self.assertNotIn("仅保留到退出", source)
        self.assertNotIn("提交规划：仅已暂存差异", source)
        self.assertNotIn("提交规划：全部工作区改动", source)
        self.assertIn("AI 提交固定分析并提交整个工作区", source)
        self.assertIn("仅本机回环 Ollama 保证源码不离开本机", source)
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
        self.assertEqual(source.count("columns: root.compact ? 1 : 2"), 1)
        self.assertIn("root.width < 760", source)
        self.assertNotIn("connectionPanel", source)
        self.assertNotIn("rulesPanel", source)
        self.assertNotIn("enabledCheck", source)
        self.assertNotIn("bodyCheck", source)

    def test_settings_fetches_models_into_combobox_selection(self) -> None:
        card_source = self._settings_qml_source()
        connection_source = (
            ROOT / "app_qml" / "qml" / "components" / "AiCommitConnectionSection.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("function onModelListFinished(provider, ok, models, message)", card_source)
        self.assertIn("AiCommitBridge.fetchModels()", card_source)
        self.assertIn("connectionSection.setAvailableModels(provider, models)", card_source)
        self.assertIn("property string _modelFetchEndpoint", card_source)
        self.assertIn("matchesCurrentConnection", card_source)
        self.assertIn("connectionSection.activeEndpoint.trim()", card_source)
        self.assertIn("root.clearModelFetchState()", card_source)
        self.assertEqual(connection_source.count("Fluent.ComboBox {"), 3)
        self.assertIn("signal fetchModelsRequested()", connection_source)
        self.assertIn("function setAvailableModels(provider, models)", connection_source)
        self.assertIn('text: root.modelsLoading ? "正在获取…"', connection_source)
        self.assertIn('? "刷新模型" : "获取模型"', connection_source)
        self.assertIn('objectName: "localModelCombo"', connection_source)
        self.assertIn('objectName: "fetchModelsButton"', connection_source)
        self.assertIn("Layout.columnSpan: connectionFields.columns", connection_source)
        self.assertNotIn(
            "connectionFields.columns === 1 ? 1 : 2", connection_source
        )
        self.assertLess(
            connection_source.index('text: "模型来源"'),
            connection_source.index('text: "服务地址"'),
        )
        self.assertLess(
            connection_source.index('text: "服务地址"'),
            connection_source.index('text: "模型名称"'),
        )
        self.assertNotIn("id: localModelInput", connection_source)
        self.assertNotIn("id: remoteModelInput", connection_source)

    def test_rules_section_exposes_only_body_generation_choice(self) -> None:
        source = (
            ROOT
            / "app_qml"
            / "qml"
            / "components"
            / "AiCommitRulesSection.qml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("id: rulesFields", source)
        self.assertNotIn("id: scopeCombo", source)
        self.assertNotIn("property alias scopeIndex", source)
        self.assertIn("id: bodyOptionLayout", source)
        self.assertIn("property alias generateBody", source)

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
