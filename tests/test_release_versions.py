# coding: utf-8
from __future__ import annotations

import re
import unittest
from pathlib import Path

from prismqml.python.tools.windows_installer import check_installer, load_manifest


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
                r'^#define PrismAppVersion "([0-9]+\.[0-9]+\.[0-9]+)"$',
            ),
        }
        self.assertEqual(len(set(versions.values())), 1, versions)

    def test_generated_windows_installer_stays_current(self) -> None:
        root = Path(__file__).resolve().parents[1]
        manifest = load_manifest(root / "prismqml-installer.json")
        version = self.extract(
            root / "app" / "common" / "setting.py",
            r'^VERSION = "v([0-9]+\.[0-9]+\.[0-9]+)"$',
        )

        result = check_installer(manifest, root / "installer.iss", version)
        installer_source = (root / "installer.iss").read_text(encoding="utf-8")

        self.assertFalse(result.changed)
        self.assertEqual(
            manifest.app_id,
            "8F3A9C2E-5B1D-4E7A-9C6F-A1B2C3D4E5F6",
        )
        self.assertEqual(manifest.aumid, "PrismQML.Gitora")
        self.assertEqual(manifest.install_scope, "machine")
        self.assertTrue(manifest.launch_after_install)
        self.assertIn("CloseApplications=yes", installer_source)
        self.assertIn("RestartApplications=no", installer_source)
        self.assertIn("Flags: nowait postinstall", installer_source)
        self.assertNotIn("skipifsilent", installer_source)

    def test_windows_release_build_bypasses_unstable_clcache(self) -> None:
        root = Path(__file__).resolve().parents[1]
        build_script = (root / "build_nuitka.py").read_text(encoding="utf-8")
        self.assertIn('"--disable-cache=ccache"', build_script)

    def test_windows_installer_e2e_is_remote_manual_and_checks_real_install(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        workflow = (
            root / ".github" / "workflows" / "windows-installer-e2e.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn('PYTHONUTF8: "1"', workflow)
        self.assertIn('PYTHONIOENCODING: "utf-8"', workflow)
        self.assertIn("python build_nuitka.py", workflow)
        self.assertIn("windows_installer compile", workflow)
        self.assertIn('"/SILENT"', workflow)
        self.assertNotIn('"/VERYSILENT"', workflow)
        self.assertIn('"/SUPPRESSMSGBOXES"', workflow)
        self.assertIn('"/NORESTART"', workflow)
        self.assertIn("Get-Process -Name Gitora", workflow)
        self.assertIn("$process.WaitForExit()", workflow)
        self.assertNotIn("-ArgumentList $arguments -Wait -PassThru", workflow)
        self.assertIn("静默安装后未自动启动新版 Gitora", workflow)
        self.assertIn("Stop-Process -Id $launchedProcess.Id", workflow)
        self.assertIn("GITORA_E2E_APP_ID", workflow)
        self.assertIn('"{$env:GITORA_E2E_APP_ID}_is1"', workflow)
        self.assertIn('$entry.DisplayName -notlike "Gitora*"', workflow)
        self.assertIn("$entry.InstallLocation", workflow)
        self.assertIn("tools/packaged_ai_connection_selftest.py", workflow)
        self.assertIn("Attach installer to Release", workflow)
        self.assertIn("gh release upload", workflow)

    def test_macos_release_keeps_stable_asset_name(self) -> None:
        root = Path(__file__).resolve().parents[1]
        workflow = (
            root / ".github" / "workflows" / "build-macos.yml"
        ).read_text(encoding="utf-8")

        self.assertIn('DEST="Gitora-macOS.dmg"', workflow)
        self.assertIn("Release tag 与应用版本不一致", workflow)
        self.assertIn("for attempt in 1 2 3", workflow)
        self.assertIn("hdiutil 连续三次创建 DMG 失败", workflow)

    @staticmethod
    def extract(path: Path, pattern: str) -> str:
        match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
        if not match:
            raise AssertionError(f"未在 {path.name} 找到版本号")
        return match.group(1)


if __name__ == "__main__":
    unittest.main()
