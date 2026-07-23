# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app_qml.backend.git_bridge import GitBridge
from tests.git_test_utils import init_repo


class GitRuleFilesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.temp_dir = tempfile.TemporaryDirectory(prefix="gitora-rule-files-")
        self.repo = init_repo(Path(self.temp_dir.name) / "repo")
        self.bridge = GitBridge()
        self.bridge._poll_timer.stop()
        self.assertTrue(
            self.bridge._svc.set_repo_path(str(self.repo), emit_status=False)
        )

    def tearDown(self) -> None:
        self.bridge.deleteLater()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def test_reads_existing_and_creates_both_rule_files(self) -> None:
        (self.repo / ".gitignore").write_text(".venv/\n", encoding="utf-8")

        self.assertEqual(self.bridge.readRepoRuleFile(".gitignore"), ".venv/\n")
        self.assertEqual(self.bridge.readRepoRuleFile(".gitattributes"), "")

        statuses: list[bool] = []
        self.bridge.statusChanged.connect(lambda: statuses.append(True))
        self.assertEqual(
            self.bridge.saveRepoRuleFile(".gitignore", ".venv/\n*.log\n"),
            [True, "已保存 .gitignore"],
        )
        self.assertEqual(
            self.bridge.saveRepoRuleFile(".gitattributes", "*.png binary\n"),
            [True, "已保存 .gitattributes"],
        )

        self.assertEqual(
            (self.repo / ".gitignore").read_text(encoding="utf-8"),
            ".venv/\n*.log\n",
        )
        self.assertEqual(
            (self.repo / ".gitattributes").read_text(encoding="utf-8"),
            "*.png binary\n",
        )
        self.assertEqual(statuses, [True, True])

    def test_rejects_unknown_or_outside_paths(self) -> None:
        self.assertEqual(self.bridge.readRepoRuleFile("settings.ini"), "")
        ok, message = self.bridge.saveRepoRuleFile("../outside", "secret")
        self.assertFalse(ok)
        self.assertIn("只允许编辑", message)
        self.assertFalse((self.repo.parent / "outside").exists())

    def test_advanced_view_exposes_editable_rule_file_controls(self) -> None:
        root = Path(__file__).resolve().parents[1]
        advanced = (root / "app_qml" / "qml" / "views" / "AdvancedView.qml").read_text(
            encoding="utf-8"
        )
        editor = (root / "app_qml" / "qml" / "components" / "RepoRuleEditor.qml").read_text(
            encoding="utf-8"
        )
        self.assertIn('fileName: ".gitignore"', advanced)
        self.assertIn('fileName: ".gitattributes"', advanced)
        self.assertIn("readRepoRuleFile", advanced)
        self.assertIn("saveRepoRuleFile", advanced)
        self.assertIn("multilineType: Fluent.Enums.input.multiline_plain", editor)
        self.assertIn("textFormat: TextEdit.PlainText", editor)
        self.assertNotIn("readOnly: true", editor)


if __name__ == "__main__":
    unittest.main()
