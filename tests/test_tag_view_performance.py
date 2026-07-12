# coding: utf-8
import unittest
from pathlib import Path


class TagViewPerformanceTest(unittest.TestCase):
    def test_large_tag_sets_use_virtualized_list_and_defer_hidden_refresh(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "app_qml"
            / "qml"
            / "views"
            / "TagView.qml"
        ).read_text(encoding="utf-8")

        self.assertIn("id: tagList", source)
        self.assertIn("ListView {", source)
        self.assertNotIn("Repeater {", source)
        self.assertIn("if (!root.visible)", source)
        self.assertIn("property bool _tagsRequesting", source)


if __name__ == "__main__":
    unittest.main()
