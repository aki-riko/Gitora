# coding: utf-8
from __future__ import annotations

import importlib.metadata
import re
import unittest
from pathlib import Path

import prismqml
from app.common.setting import _resolve_installer_silent_args
from prismqml import App


ROOT = Path(__file__).resolve().parents[1]


class EngineAutoUpdateContractTest(unittest.TestCase):
    def test_required_engine_version_is_installed_with_auto_updater(self) -> None:
        requirements = (
            ROOT / "app_qml" / "requirements.txt"
        ).read_text(encoding="utf-8")
        match = re.search(r"^prismqml==([^\s]+)$", requirements, re.MULTILINE)

        self.assertIsNotNone(match)
        expected_version = match.group(1)
        self.assertEqual(importlib.metadata.version("prismqml"), expected_version)
        self.assertTrue(callable(App.enable_auto_update))
        self.assertTrue(
            (prismqml.qml_path() / "controls" / "feedback" / "AutoUpdater.qml").is_file()
        )
        self.assertIn(
            "AutoUpdater controls/feedback/AutoUpdater.qml",
            (prismqml.qml_path() / "qmldir").read_text(encoding="utf-8"),
        )

    def test_python_entry_uses_engine_auto_update_wiring(self) -> None:
        source = (ROOT / "app_qml" / "main_qml.py").read_text(encoding="utf-8")

        self.assertIn(
            "app.enable_auto_update(UPDATE_REPO, VERSION, UPDATE_ASSET_KEYWORD)",
            source,
        )
        self.assertNotIn("from prismqml import Updater", source)
        self.assertNotIn('setContextProperty("Updater"', source)
        self.assertNotIn("app._updater =", source)

    def test_qml_uses_one_engine_auto_updater_facade(self) -> None:
        main_source = (
            ROOT / "app_qml" / "qml" / "main.qml"
        ).read_text(encoding="utf-8")
        settings_source = (
            ROOT / "app_qml" / "qml" / "views" / "SettingsView.qml"
        ).read_text(encoding="utf-8")

        self.assertEqual(main_source.count("Fluent.AutoUpdater {"), 1)
        self.assertIn("property Item autoUpdaterHost: Item {", main_source)
        self.assertIn("parent: appWindow.contentItem", main_source)
        self.assertIn("running: !GitoraSelftestMode", main_source)
        self.assertIn("updater: appUpdater", main_source)
        self.assertIn("silentArgs: AppInfo ? AppInfo.installerSilentArgs", main_source)
        self.assertIn("autoUpdater.checkSilently()", main_source)
        self.assertNotIn("autoUpdater.notifyWhenUpToDate", main_source)
        self.assertIn("Window.window.autoUpdaterController", settings_source)
        self.assertIn("root._autoUpdater.check()", settings_source)
        self.assertIn("root._autoUpdater.notifyWhenUpToDate = true", settings_source)
        self.assertNotIn("Updater.checkForUpdate()", settings_source)
        self.assertNotIn("target: typeof Updater", settings_source)

    def test_qml_uses_the_engine_owned_splash_instance(self) -> None:
        main_source = (
            ROOT / "app_qml" / "qml" / "main.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("splashComponent: root.splashComponent", main_source)
        self.assertNotIn("this._splashInstance =", main_source)
        self.assertNotIn("root.splashComponent.createObject", main_source)

    def test_settings_appearance_follows_persistent_engine_config(self) -> None:
        settings_source = (
            ROOT / "app_qml" / "qml" / "views" / "SettingsView.qml"
        ).read_text(encoding="utf-8")
        main_source = (ROOT / "app_qml" / "main_qml.py").read_text(
            encoding="utf-8"
        )

        for contract in (
            'objectName: "themeSettingsCard"',
            "ConfigManager ? ConfigManager.themeOptions : []",
            "themeValues.indexOf(ConfigManager.theme)",
            "ConfigManager.setTheme(themeValues[idx])",
            'objectName: "skinSettingsCard"',
            "ConfigManager ? ConfigManager.skinOptions : []",
            "skinValues.indexOf(ConfigManager.skin)",
            "ConfigManager.setSkin(skinValues[idx])",
        ):
            self.assertIn(contract, settings_source)
        self.assertNotIn("ThemeManager.setThemeFromQml", settings_source)
        self.assertIn("_validate_appearance_settings(stack)", main_source)
        self.assertIn('page_loader.property("item")', main_source)
        self.assertIn('(\"themeSettingsCard\",', main_source)
        self.assertIn('(\"skinSettingsCard\",', main_source)

    def test_installed_engine_exposes_in_place_download_feedback(self) -> None:
        feedback_dir = prismqml.qml_path() / "controls" / "feedback"
        facade_source = (feedback_dir / "AutoUpdater.qml").read_text(
            encoding="utf-8"
        )
        presenter_source = (
            feedback_dir / "AutoUpdaterToastPresenter.qml"
        ).read_text(encoding="utf-8")
        signal_source = (
            feedback_dir / "_internal" / "AutoUpdaterSignalConnections.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("function checkSilently()", facade_source)
        self.assertIn("FeedbackInternal.AutoUpdaterSignalConnections", facade_source)
        self.assertIn("host._formatSize(received)", signal_source)
        self.assertIn("host._formatSize(total)", signal_source)
        self.assertNotIn("item.show();", presenter_source)
        self.assertEqual(
            _resolve_installer_silent_args("nt"),
            "/SILENT /SUPPRESSMSGBOXES /NORESTART /SP-",
        )
        self.assertEqual(_resolve_installer_silent_args("posix"), "")

    def test_installed_timeline_selection_uses_render_thread_animators(self) -> None:
        timeline_dir = prismqml.qml_path() / "controls" / "containers"
        card_source = (
            timeline_dir / "_internal" / "TimelineVirtualRow.qml"
        ).read_text(encoding="utf-8")
        graph_source = (timeline_dir / "TimelineGraphLayer.qml").read_text(
            encoding="utf-8"
        )

        self.assertIn('objectName: "timelineCardSelectionIndicator"', card_source)
        self.assertNotIn("Behavior on height", card_source)
        self.assertIn("OpacityAnimator", card_source)
        self.assertIn("ScaleAnimator", card_source)
        self.assertIn('objectName: "timelineGraphSelectionRing"', graph_source)
        self.assertIn("OpacityAnimator", graph_source)
        self.assertIn("ScaleAnimator", graph_source)

    def test_custom_notification_host_no_longer_owns_update_flow(self) -> None:
        source = (
            ROOT / "app_qml" / "qml" / "components" / "ToastProgressHost.qml"
        ).read_text(encoding="utf-8")

        for removed_contract in (
            "Updater",
            "UpdateDialog",
            "_downloadToast",
            "_updateSilent",
            "_downloadUrl",
            "_htmlUrl",
            "downloadUpdate",
            "onDownloadProgress",
            "onDownloadFinished",
            "onDownloadFailed",
            "runInstallerAndQuit",
        ):
            self.assertNotIn(removed_contract, source)
        self.assertIn("function onProgressUpdated(percent, message)", source)
        self.assertIn("function onConnectionTestFinished(ok, message)", source)


if __name__ == "__main__":
    unittest.main()
