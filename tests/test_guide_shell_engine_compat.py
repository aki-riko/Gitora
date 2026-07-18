# coding: utf-8
from __future__ import annotations

import unittest
from pathlib import Path


class GuideShellEngineCompatTest(unittest.TestCase):
    def test_pages_use_current_stacked_widget_container_api(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "app_qml" / "qml" / "components" / "GuideShell.qml").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("stack.pageComponents", source)
        self.assertIn("property list<Component> pageComponents", source)
        self.assertIn("parent: stack.containerItem", source)


if __name__ == "__main__":
    unittest.main()
