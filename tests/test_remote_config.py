# coding: utf-8
"""远程抓取/推送双地址的真实 Git 配置回归测试。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.git_service import GitService

from git_test_utils import init_repo, run_git


class RemoteConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def service_for(self, repo: Path) -> GitService:
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo)))
        return service

    def test_remote_config_supports_separate_fetch_and_push_urls(self) -> None:
        repo = init_repo(self.root / "repo")
        fetch_url = "https://gitee.example/Aquila/Gitora.git"
        push_url = "ssh://git@9li.example:28022/Aquila/Gitora.git"
        run_git(repo, "remote", "add", "origin", fetch_url)
        service = self.service_for(repo)

        self.assertEqual(
            service.get_remote_config_info(),
            [("origin", fetch_url, fetch_url)],
        )

        ok, message = service.set_remote_urls("origin", fetch_url, push_url)
        self.assertTrue(ok, message)
        self.assertEqual(
            service.get_remote_config_info(),
            [("origin", fetch_url, push_url)],
        )
        self.assertEqual(
            run_git(repo, "config", "--get-all", "remote.origin.pushurl").stdout.strip(),
            push_url,
        )

        changed_fetch_url = "https://gitee.example/Aquila/Gitora-mirror.git"
        ok, message = service.set_remote_url("origin", changed_fetch_url)
        self.assertTrue(ok, message)
        self.assertEqual(
            service.get_remote_config_info(),
            [("origin", changed_fetch_url, push_url)],
        )

        ok, message = service.set_remote_push_url("origin", "")
        self.assertTrue(ok, message)
        self.assertEqual(
            service.get_remote_config_info(),
            [("origin", changed_fetch_url, changed_fetch_url)],
        )
        self.assertNotEqual(
            run_git(repo, "config", "--get-all", "remote.origin.pushurl", check=False).returncode,
            0,
        )


if __name__ == "__main__":
    unittest.main()
