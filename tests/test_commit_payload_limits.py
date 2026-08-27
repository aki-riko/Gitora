"""提交详情的展示载荷必须有界。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.git_service import (
    MAX_BRANCH_RESULTS,
    MAX_CLEAN_PREVIEW,
    MAX_CONFLICT_FILE_SIZE,
    MAX_COMMIT_DIFF_SIZE,
    MAX_COMMIT_FILE_PREVIEW,
    GitService,
)
from tests.git_test_utils import commit_all, init_repo, write_file
from app_qml.backend.git_bridge import GitBridge


class CommitPayloadLimitsTest(unittest.TestCase):
    def test_commit_file_preview_reports_total_without_returning_all_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gitora-commit-files-") as temp_dir:
            repo = init_repo(Path(temp_dir) / "repo")
            write_file(repo, "base.txt", "base\n")
            commit_all(repo, "base")
            total = MAX_COMMIT_FILE_PREVIEW + 37
            for index in range(total):
                write_file(repo, f"files/file-{index:04d}.txt", "content\n")
            commit_hash = commit_all(repo, "large file set")
            service = GitService()
            service.set_repo_path(str(repo), emit_status=False)

            files, reported_total, truncated = service.get_commit_files_preview(
                commit_hash
            )

            self.assertEqual(len(files), MAX_COMMIT_FILE_PREVIEW)
            self.assertEqual(reported_total, total)
            self.assertTrue(truncated)

    def test_commit_diff_is_capped_for_ui_and_supports_single_file_scope(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gitora-commit-diff-") as temp_dir:
            repo = init_repo(Path(temp_dir) / "repo")
            write_file(repo, "large.txt", "base\n")
            commit_all(repo, "base")
            write_file(repo, "large.txt", "x\n" * 100_000)
            commit_hash = commit_all(repo, "large diff")
            service = GitService()
            service.set_repo_path(str(repo), emit_status=False)

            full_scope_diff = service.get_commit_diff(commit_hash)
            file_scope_diff = service.get_commit_diff(commit_hash, "large.txt")

            self.assertLessEqual(len(full_scope_diff), MAX_COMMIT_DIFF_SIZE)
            self.assertLessEqual(len(file_scope_diff), MAX_COMMIT_DIFF_SIZE)
            self.assertIn("[内容过大，已截断", full_scope_diff)
            self.assertIn("diff --git a/large.txt b/large.txt", file_scope_diff)

    def test_history_query_does_not_fold_deep_skip_back_to_the_limit(self) -> None:
        service = GitService()
        calls: list[list[str]] = []

        def fake_run(*args, **kwargs):
            calls.append(list(args[1]))
            return True, "", ""

        service._run_git_sync_at = fake_run  # type: ignore[method-assign]

        self.assertEqual(service.get_graph_log_at("repo", 30, 2001), [])
        self.assertEqual(calls, [])

    def test_branch_query_caps_combined_local_and_remote_results(self) -> None:
        service = GitService()
        local = "\n".join(
            f"local-{index} abcdef1" for index in range(MAX_BRANCH_RESULTS + 20)
        )
        remote = "origin/remote-0\n"
        calls = [local, remote]

        def fake_run(*args, **kwargs):
            return True, calls.pop(0), ""

        service._run_git_sync = fake_run  # type: ignore[method-assign]

        self.assertEqual(len(service.get_branches()), MAX_BRANCH_RESULTS)

    def test_clean_preview_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gitora-clean-preview-") as temp_dir:
            repo = init_repo(Path(temp_dir) / "repo")
            for index in range(MAX_CLEAN_PREVIEW + 11):
                write_file(repo, f"untracked-{index:04d}.txt", "x\n")
            service = GitService()
            service.set_repo_path(str(repo), emit_status=False)

            files, total, truncated = service.clean_preview_limited()

            self.assertEqual(len(files), MAX_CLEAN_PREVIEW)
            self.assertEqual(total, MAX_CLEAN_PREVIEW + 11)
            self.assertTrue(truncated)

    def test_conflict_file_reader_caps_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="gitora-conflict-file-") as temp_dir:
            repo = init_repo(Path(temp_dir) / "repo")
            payload = "x" * (MAX_CONFLICT_FILE_SIZE + 10)
            write_file(repo, "conflict.txt", payload)

            content, truncated = GitBridge._read_conflict_file_at(
                str(repo), "conflict.txt"
            )

            self.assertEqual(len(content), MAX_CONFLICT_FILE_SIZE)
            self.assertTrue(truncated)


if __name__ == "__main__":
    unittest.main()
