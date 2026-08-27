"""提交详情的展示载荷必须有界。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.common.git_service import (
    MAX_COMMIT_DIFF_SIZE,
    MAX_COMMIT_FILE_PREVIEW,
    GitService,
)
from tests.git_test_utils import commit_all, init_repo, write_file


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


if __name__ == "__main__":
    unittest.main()
