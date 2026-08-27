# coding: utf-8
from __future__ import annotations

import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
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

    def test_python_entry_primes_fast_splash_branding_before_app(self) -> None:
        source = (ROOT / "app_qml" / "main_qml.py").read_text(encoding="utf-8")

        app_index = source.index("    app = App(")
        display_name_index = source.index(
            "    QGuiApplication.setApplicationDisplayName(APP_NAME)"
        )
        icon_argument_index = source.index(
            "        application_icon=APP_LOGO_PATH"
        )

        self.assertLess(display_name_index, app_index)
        self.assertLess(icon_argument_index, source.index("        config_path=", app_index))
        self.assertIn("from PySide6.QtGui import QGuiApplication", source)
        self.assertIn("APP_NAME,", source)
        self.assertIn("APP_LOGO_PATH = os.path.join(", source)

    def test_python_entry_prefers_local_engine_source_in_development(self) -> None:
        source = (ROOT / "app_qml" / "main_qml.py").read_text(encoding="utf-8")

        self.assertIn("if not _is_frozen():", source)
        self.assertIn('env = os.environ.get("PRISMQML_ROOT")', source)
        self.assertIn('os.path.join(parent, "PrismQML")', source)
        self.assertIn("# 回退:已安装或打包内置的 prismqml", source)
        self.assertLess(
            source.index('env = os.environ.get("PRISMQML_ROOT")'),
            source.index("import prismqml as _f"),
        )

    def test_python_entry_uses_gitora_owned_engine_config(self) -> None:
        source = (ROOT / "app_qml" / "main_qml.py").read_text(
            encoding="utf-8"
        )
        setting_source = (ROOT / "app" / "common" / "setting.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            'PRISMQML_CONFIG_FILE = CONFIG_FOLDER / "prismqml.json"',
            setting_source,
        )
        self.assertIn("config_path=PRISMQML_CONFIG_FILE", source)
        self.assertIn("persist_appearance=True", source)
        self.assertIn("getConfigManager(\n        str(PRISMQML_CONFIG_FILE)", source)

    def test_gitora_config_wins_when_gallery_config_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            gallery_path = temporary_root / "gallery.json"
            gitora_path = temporary_root / "local" / "Gitora" / "prismqml.json"
            gitora_path.parent.mkdir(parents=True)
            gallery_path.write_text(
                json.dumps(
                    {
                        "Appearance": {
                            "Theme": "dark",
                            "Skin": "vintage_ticket",
                            "Language": "zh_CN",
                            "AccentColor": "#123456",
                        }
                    }
                ),
                encoding="utf-8",
            )
            gitora_path.write_text(
                json.dumps(
                    {
                        "Appearance": {
                            "Theme": "light",
                            "Skin": "fluent",
                            "Language": "en",
                            "AccentColor": "#654321",
                        }
                    }
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment.update(
                {
                    "LOCALAPPDATA": str(temporary_root / "local"),
                    "PRISMQML_CONFIG_FILE": str(gallery_path),
                    "PYTHONIOENCODING": "utf-8",
                    "QT_QPA_PLATFORM": "offscreen",
                }
            )
            script = """
from pathlib import Path
from PySide6.QtCore import QTimer
from app.common.setting import PRISMQML_CONFIG_FILE
from prismqml import App
from prismqml.python.config import getConfigManager

app = App([], config_path=PRISMQML_CONFIG_FILE, persist_appearance=True)
manager = getConfigManager(str(PRISMQML_CONFIG_FILE), persist_appearance=True)
assert Path(manager.getConfigPath()).resolve() == PRISMQML_CONFIG_FILE.resolve()
assert manager.theme == "light"
assert manager.skin == "fluent"
assert manager.language == "en"
assert manager.accentColor == "#654321"
QTimer.singleShot(0, app.quit)
raise SystemExit(app.exec())
"""
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
