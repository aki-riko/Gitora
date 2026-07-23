# coding: utf-8
"""Gitora business cards must consume the PrismQML inset exactly once."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QML_ROOT = ROOT / "app_qml" / "qml"
CARD_FILES = {
    "views/AdvancedView.qml": 6,
    "views/BranchView.qml": 2,
    "views/ConflictView.qml": 2,
    "views/StashView.qml": 1,
    "views/TagView.qml": 1,
    "components/RepoRuleEditor.qml": 1,
    "components/ReflogDialog.qml": 1,
}


class CardLayoutContractTest(unittest.TestCase):
    def test_business_cards_do_not_repeat_engine_content_padding(self) -> None:
        for relative_path, expected_count in CARD_FILES.items():
            source = (QML_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertEqual(
                len(re.findall(r"\bFluent\.Card\s*\{", source)),
                expected_count,
                relative_path,
            )
            self.assertNotRegex(
                source,
                r"anchors\.margins:\s*Fluent\.Enums\.spacing\.(?:l|m)\b",
                relative_path,
            )

    def test_special_card_geometry_uses_the_engine_inset(self) -> None:
        conflict_source = (QML_ROOT / "views" / "ConflictView.qml").read_text(
            encoding="utf-8"
        )
        reflog_source = (
            QML_ROOT / "components" / "ReflogDialog.qml"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "width: parent.width - Fluent.Enums.spacing.l * 2", conflict_source
        )
        self.assertIn(
            "itemHeight: Fluent.Enums.controlSize.buttonHeight "
            "+ Fluent.Enums.spacing.l * 2",
            reflog_source,
        )


if __name__ == "__main__":
    unittest.main()
