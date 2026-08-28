# coding: utf-8
"""关于页面的年份与 PrismQML 行内链接展示合同。"""

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AboutSettingsQmlContractTest(unittest.TestCase):
    def test_about_metadata_exposes_2026_and_prismqml_link(self) -> None:
        setting_source = (ROOT / "app" / "common" / "setting.py").read_text(
            encoding="utf-8"
        )
        main_source = (ROOT / "app_qml" / "main_qml.py").read_text(
            encoding="utf-8"
        )
        settings_source = (
            ROOT / "app_qml" / "qml" / "views" / "SettingsView.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("YEAR = 2026", setting_source)
        self.assertIn(
            'PRISMQML_URL = "https://github.com/aki-riko/PrismQML"',
            setting_source,
        )
        self.assertIn("PRISMQML_URL", main_source)
        self.assertIn('"prismQmlUrl": PRISMQML_URL', main_source)
        self.assertIn('objectName: "aboutSettingsCard"', settings_source)
        self.assertIn('objectName: "prismQmlHomepageLink"', settings_source)
        self.assertIn("type: Fluent.Enums.label.type_hyperlink", settings_source)
        self.assertIn('text: "PrismQML"', settings_source)
        self.assertIn(
            'url: AppInfo ? AppInfo.prismQmlUrl : ""', settings_source
        )
        self.assertIn(" · 基于", settings_source)
        self.assertIn('text: "引擎构建。"', settings_source)


if __name__ == "__main__":
    unittest.main()
