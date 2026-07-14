from pathlib import Path
import unittest


class RepoViewPerformanceTest(unittest.TestCase):
    def test_change_list_uses_backend_model_and_reuses_delegates(self) -> None:
        source = Path("app_qml/qml/views/RepoView.qml").read_text(encoding="utf-8")

        self.assertIn("GitBridge.fileChangeModel", source)
        self.assertIn("reuseItems: true", source)
        self.assertNotIn("ListModel { id: changeModel }", source)
        self.assertNotIn("changeModel.append", source)


if __name__ == "__main__":
    unittest.main()
