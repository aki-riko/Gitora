# coding: utf-8
import unittest

from app.common.git_service import FileChange, FileStatus
from app_qml.backend.file_change_model import FileChangeListModel


class FileChangeListModelTest(unittest.TestCase):
    def test_replace_exposes_roles_and_contains(self) -> None:
        model = FileChangeListModel()
        items = [
            FileChange("src/main.py", FileStatus.MODIFIED, False),
            FileChange("README.md", FileStatus.ADDED, True),
        ]

        model.replace(items)

        self.assertEqual(model.count, 2)
        first = model.index(0, 0)
        self.assertEqual(model.data(first, model.PathRole), "src/main.py")
        self.assertEqual(model.data(first, model.StatusRole), "M")
        self.assertEqual(model.data(first, model.StatusTextRole), "已修改")
        self.assertFalse(model.data(first, model.StagedRole))
        self.assertTrue(model.contains("README.md", True))
        self.assertFalse(model.contains("README.md", False))

    def test_clear_resets_count(self) -> None:
        model = FileChangeListModel()
        model.replace([FileChange("new.txt", FileStatus.UNTRACKED, False)])

        model.clear()

        self.assertEqual(model.count, 0)


if __name__ == "__main__":
    unittest.main()
