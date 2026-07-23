# coding: utf-8
from __future__ import annotations

import importlib.metadata
import re
import unittest
from pathlib import Path

import prismqml
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
        self.assertIn("updater: appUpdater", main_source)
        self.assertIn("silentArgs: AppInfo ? AppInfo.installerSilentArgs", main_source)
        self.assertIn("autoUpdater.check()", main_source)
        self.assertIn("Window.window.autoUpdaterController", settings_source)
        self.assertIn("root._autoUpdater.check()", settings_source)
        self.assertIn("root._autoUpdater.notifyWhenUpToDate = true", settings_source)
        self.assertNotIn("Updater.checkForUpdate()", settings_source)
        self.assertNotIn("target: typeof Updater", settings_source)

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
