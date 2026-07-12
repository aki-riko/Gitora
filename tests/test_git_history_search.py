# coding: utf-8
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.git_service import GitService

from git_test_utils import commit_all, configure_user, init_repo, run_git, write_file


class GitHistorySearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_search_repo(self) -> tuple[GitService, str, str, str]:
        repo = init_repo(self.root / "repo")
        run_git(repo, "config", "user.name", "Search Needle")
        write_file(repo, "history.txt", "initial\n")
        initial = commit_all(repo, "initial setup")

        run_git(repo, "config", "user.name", "Hash Author")
        write_file(repo, "history.txt", "target\n")
        target = commit_all(repo, "Search Needle target " + "0" * 40)
        write_file(repo, "history.txt", "newest\n")
        newest = commit_all(repo, "Hash Author newest")

        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo), emit_status=False))
        return service, initial, target, newest

    def test_all_search_merges_message_and_author_without_duplicates(self) -> None:
        service, initial, target, newest = self.make_search_repo()

        merged_results = service.search_commits("Search Needle", "all", 20)
        self.assertEqual([item.hash for item in merged_results], [target, initial])

        deduplicated_results = service.search_commits("Hash Author", "all", 20)
        self.assertEqual([item.hash for item in deduplicated_results], [newest, target])

    def test_all_search_resolves_short_and_full_hash(self) -> None:
        service, initial, target, _ = self.make_search_repo()

        short_results = service.search_commits(initial[:7].upper(), "all", 20)
        self.assertEqual([item.hash for item in short_results], [initial])

        full_results = service.search_commits(target, "all", 20)
        self.assertEqual([item.hash for item in full_results], [target])

    def test_hash_shaped_message_falls_back_to_text_search(self) -> None:
        service, _, target, _ = self.make_search_repo()
        zero_hash = "0" * 40

        results = service.search_commits(zero_hash, "all", 20)
        self.assertEqual([item.hash for item in results], [target])

    def test_all_search_respects_result_limit(self) -> None:
        service, _, target, _ = self.make_search_repo()

        results = service.search_commits("Search Needle", "all", 1)
        self.assertEqual([item.hash for item in results], [target])

    def test_hex_branch_name_is_not_treated_as_commit_hash(self) -> None:
        service, _, _, newest = self.make_search_repo()
        run_git(self.root / "repo", "branch", "dead", newest)

        self.assertEqual(service.search_commits("dead", "all", 20), [])

    def test_hash_search_stays_within_current_head_history(self) -> None:
        service, initial, _, _ = self.make_search_repo()
        repo = self.root / "repo"
        run_git(repo, "checkout", "-b", "side", initial)
        write_file(repo, "side.txt", "side\n")
        side_commit = commit_all(repo, "side only")
        run_git(repo, "checkout", "master")

        self.assertEqual(service.search_commits(side_commit[:7], "all", 20), [])

    def test_text_search_treats_query_as_literal_text(self) -> None:
        repo = init_repo(self.root / "literal")
        run_git(repo, "config", "user.name", "Literal [Author]")
        write_file(repo, "literal.txt", "literal\n")
        commit_hash = commit_all(repo, "literal [message]")
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo), emit_status=False))

        for search_type in ("all", "message", "author"):
            results = service.search_commits("[", search_type, 20)
            self.assertEqual([item.hash for item in results], [commit_hash])

    def test_hash_search_supports_sha256_repositories(self) -> None:
        repo = self.root / "sha256"
        repo.mkdir()
        init_result = run_git(
            repo, "-c", "init.defaultBranch=master", "init",
            "--object-format=sha256", check=False,
        )
        if init_result.returncode != 0:
            self.skipTest("当前 Git 不支持 SHA-256 仓库")

        configure_user(repo)
        write_file(repo, "sha256.txt", "sha256\n")
        commit_hash = commit_all(repo, "sha256 history")
        self.assertEqual(len(commit_hash), 64)
        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo), emit_status=False))

        for query in (commit_hash[:7].upper(), commit_hash):
            results = service.search_commits(query, "all", 20)
            self.assertEqual([item.hash for item in results], [commit_hash])

    def test_search_keeps_initial_repository_snapshot(self) -> None:
        repo_a = init_repo(self.root / "repo-a")
        write_file(repo_a, "a.txt", "a\n")
        expected_hash = commit_all(repo_a, "snapshot target")
        repo_b = init_repo(self.root / "repo-b")
        write_file(repo_b, "b.txt", "b\n")
        commit_all(repo_b, "other repository")

        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo_a), emit_status=False))
        original_run = service._run_git_sync_at
        seen_repos: list[str] = []

        def switching_run(repo_path: str, args: list[str], timeout: int = 30):
            seen_repos.append(repo_path)
            if len(seen_repos) == 1:
                service.set_repo_path(str(repo_b), emit_status=False)
            return original_run(repo_path, args, timeout)

        service._run_git_sync_at = switching_run  # type: ignore[method-assign]
        results = service.search_commits("snapshot target", "all", 20)

        self.assertEqual([item.hash for item in results], [expected_hash])
        self.assertEqual(set(seen_repos), {str(repo_a)})


if __name__ == "__main__":
    unittest.main()
