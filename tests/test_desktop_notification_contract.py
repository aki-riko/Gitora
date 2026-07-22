# coding: utf-8
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = ROOT / "app_qml" / "qml"


class DesktopNotificationContractTest(unittest.TestCase):
    def test_business_notifications_use_desktop_wrapper_only(self) -> None:
        legacy_calls: list[str] = []
        desktop_calls = 0
        for path in QML_ROOT.rglob("*.qml"):
            source = path.read_text(encoding="utf-8")
            if "NotificationManager.toast." in source:
                legacy_calls.append(str(path.relative_to(ROOT)))
            desktop_calls += source.count("NotificationManager.desktop.")

        self.assertEqual(legacy_calls, [])
        self.assertGreater(desktop_calls, 0)

    def test_progress_notifications_use_desktop_feature_options(self) -> None:
        source = (
            QML_ROOT / "components" / "ToastProgressHost.qml"
        ).read_text(encoding="utf-8")

        self.assertNotIn("NotificationManager.toast.", source)
        self.assertIn("NotificationManager.desktop.info(", source)
        self.assertIn('"feature": feature', source)
        self.assertIn('"progress": 0', source)


if __name__ == "__main__":
    unittest.main()
