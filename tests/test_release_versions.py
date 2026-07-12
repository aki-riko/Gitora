# coding: utf-8
from __future__ import annotations

import re
import unittest
from pathlib import Path


class ReleaseVersionTest(unittest.TestCase):
    def test_release_versions_stay_in_sync(self) -> None:
        root = Path(__file__).resolve().parents[1]
        versions = {
            "setting.py": self.extract(
                root / "app" / "common" / "setting.py",
                r'^VERSION = "v([0-9]+\.[0-9]+\.[0-9]+)"$',
            ),
            "build_nuitka.py": self.extract(
                root / "build_nuitka.py",
                r'"--product-version=([0-9]+\.[0-9]+\.[0-9]+)"',
            ),
            "build_nuitka_mac.py": self.extract(
                root / "build_nuitka_mac.py",
                r'"--product-version=([0-9]+\.[0-9]+\.[0-9]+)"',
            ),
            "installer.iss": self.extract(
                root / "installer.iss",
                r'^#define MyAppVersion "([0-9]+\.[0-9]+\.[0-9]+)"$',
            ),
        }
        self.assertEqual(len(set(versions.values())), 1, versions)

    @staticmethod
    def extract(path: Path, pattern: str) -> str:
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        if not match:
            raise AssertionError(f"未在 {path.name} 找到版本号")
        return match.group(1)


if __name__ == "__main__":
    unittest.main()
