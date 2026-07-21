# coding: utf-8
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from app.common.ai_commit_context import ChangeContextCollector, SnapshotLimits
from app.common.git_service import GitService
from tests.git_test_utils import (
    commit_all, configure_user, init_repo, run_git, write_file,
)


class AiCommitContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo = init_repo(Path(self.temp_dir.name) / "repo")
        write_file(self.repo, "tracked.txt", "base\n")
        write_file(self.repo, "AGENTS.md", "提交标题使用中文\n")
        commit_all(self.repo, "chore: 初始化")
        self.service = GitService()

    @staticmethod
    def limits(**overrides: int) -> SnapshotLimits:
        values = {
            "max_total_chars": 200_000,
            "max_file_chars": 100_000,
            "max_untracked_chars": 50_000,
            "max_instruction_chars": 20_000,
            "max_files": 100,
            "history_count": 20,
        }
        values.update(overrides)
        return SnapshotLimits(**values, instruction_files=("AGENTS.md", "CONTRIBUTING.md"))

    def make_mixed_changes(self) -> None:
        write_file(self.repo, "tracked.txt", "staged\n")
        run_git(self.repo, "add", "tracked.txt")
        write_file(self.repo, "tracked.txt", "staged\nunstaged\n")
        write_file(self.repo, "新 文件.txt", "未跟踪内容\n")
        (self.repo / "binary.bin").write_bytes(b"\x00\x01\x02")

    def test_collects_real_staged_unstaged_untracked_and_binary_without_writes(self) -> None:
        self.make_mixed_changes()
        before_head = run_git(self.repo, "rev-parse", "HEAD").stdout.strip()
        before_index = hashlib.sha256((self.repo / ".git" / "index").read_bytes()).hexdigest()
        before_status = run_git(self.repo, "status", "--porcelain=v1", "-uall").stdout

        collector = ChangeContextCollector(self.service, self.limits())
        first = collector.collect(str(self.repo), include_unstaged=True)
        second = collector.collect(str(self.repo), include_unstaged=True)

        tracked = [change for change in first.changes if change.path == "tracked.txt"]
        self.assertEqual({change.staged for change in tracked}, {True, False})
        self.assertEqual(len({change.change_id for change in tracked}), 2)
        self.assertTrue(all(change.hunks for change in tracked))
        self.assertIn("未跟踪内容", next(
            change.patch for change in first.changes if change.path == "新 文件.txt"
        ))
        binary = next(change for change in first.changes if change.path == "binary.bin")
        self.assertTrue(binary.binary)
        self.assertEqual(binary.unsupported_reason, "二进制未跟踪文件")
        self.assertEqual(first.instructions, (("AGENTS.md", "提交标题使用中文\n"),))
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(first.workspace_fingerprint, second.workspace_fingerprint)

        self.assertEqual(run_git(self.repo, "rev-parse", "HEAD").stdout.strip(), before_head)
        self.assertEqual(
            hashlib.sha256((self.repo / ".git" / "index").read_bytes()).hexdigest(),
            before_index,
        )
        self.assertEqual(
            run_git(self.repo, "status", "--porcelain=v1", "-uall").stdout,
            before_status,
        )

    def test_staged_only_scope_excludes_unstaged_and_untracked_changes(self) -> None:
        self.make_mixed_changes()
        snapshot = ChangeContextCollector(self.service, self.limits()).collect(
            str(self.repo), include_unstaged=False
        )

        self.assertEqual(len(snapshot.changes), 1)
        self.assertTrue(snapshot.changes[0].staged)
        self.assertEqual(snapshot.changes[0].path, "tracked.txt")
        self.assertFalse(snapshot.include_unstaged)

    def test_fingerprint_changes_when_untracked_content_changes(self) -> None:
        write_file(self.repo, "new.txt", "first\n")
        collector = ChangeContextCollector(self.service, self.limits())
        before = collector.workspace_fingerprint(str(self.repo))
        write_file(self.repo, "new.txt", "second\n")
        after = collector.workspace_fingerprint(str(self.repo))
        self.assertNotEqual(before, after)

    def test_limits_mark_snapshot_incomplete_and_remove_hunk_content(self) -> None:
        write_file(self.repo, "tracked.txt", "changed line with more content\n")
        snapshot = ChangeContextCollector(
            self.service,
            self.limits(max_total_chars=12, max_file_chars=12, max_untracked_chars=12),
        ).collect(str(self.repo), include_unstaged=True)

        self.assertFalse(snapshot.complete)
        self.assertTrue(snapshot.changes[0].truncated)
        self.assertEqual(snapshot.changes[0].hunks, ())
        self.assertLessEqual(len(snapshot.changes[0].patch), 12)

    def test_raw_diff_api_is_not_limited_by_ui_diff_cap(self) -> None:
        large = "x" * (110 * 1024) + "\n"
        write_file(self.repo, "tracked.txt", large)
        ok, raw, error = self.service.get_raw_diff_at(str(self.repo), staged=False)
        self.assertTrue(ok, error)
        self.assertGreater(len(raw), 100 * 1024)
        self.assertNotIn("Diff过大，已截断", raw)

    def test_conflicted_changes_are_never_marked_executable(self) -> None:
        run_git(self.repo, "checkout", "-b", "topic")
        write_file(self.repo, "tracked.txt", "topic\n")
        commit_all(self.repo, "feat: topic")
        run_git(self.repo, "checkout", "master")
        write_file(self.repo, "tracked.txt", "master\n")
        commit_all(self.repo, "fix: master")
        merge = run_git(self.repo, "merge", "topic", check=False)
        self.assertNotEqual(merge.returncode, 0)

        snapshot = ChangeContextCollector(self.service, self.limits()).collect(
            str(self.repo), include_unstaged=True
        )
        conflicts = [change for change in snapshot.changes if change.path == "tracked.txt"]
        self.assertTrue(conflicts)
        self.assertTrue(all(
            change.unsupported_reason == "存在未解决冲突" for change in conflicts
        ))
        self.assertTrue(all(not change.executable for change in conflicts))

    def test_submodule_change_is_never_marked_executable(self) -> None:
        sub = init_repo(Path(self.temp_dir.name) / "sub")
        write_file(sub, "value.txt", "one\n")
        commit_all(sub, "chore: sub one")
        run_git(
            self.repo, "-c", "protocol.file.allow=always",
            "submodule", "add", str(sub), "deps/sub",
        )
        commit_all(self.repo, "chore: add submodule")
        configure_user(self.repo / "deps" / "sub")
        write_file(self.repo / "deps" / "sub", "value.txt", "two\n")
        commit_all(self.repo / "deps" / "sub", "chore: sub two")

        snapshot = ChangeContextCollector(self.service, self.limits()).collect(
            str(self.repo), include_unstaged=True
        )
        change = next(item for item in snapshot.changes if item.path == "deps/sub")
        self.assertEqual(change.unsupported_reason, "子模块改动")
        self.assertFalse(change.executable)

    def test_instruction_and_history_share_configured_total_budget(self) -> None:
        limits = self.limits(
            max_total_chars=12,
            max_file_chars=12,
            max_instruction_chars=5,
        )
        snapshot = ChangeContextCollector(self.service, limits).collect(
            str(self.repo), include_unstaged=True
        )
        self.assertEqual(snapshot.instructions, (("AGENTS.md", "提交标题使"),))
        self.assertFalse(snapshot.complete)
        payload_chars = sum(len(content) for _, content in snapshot.instructions)
        payload_chars += sum(len(title) for title in snapshot.recent_titles)
        self.assertLessEqual(payload_chars, 12)
        self.assertTrue(any("配置上限" in warning for warning in snapshot.warnings))

    def test_hunk_id_ignores_staging_layer_and_header_line_offsets(self) -> None:
        write_file(
            self.repo,
            "stable.txt",
            "top\n" + "middle\n" * 12 + "bottom\n",
        )
        commit_all(self.repo, "chore: add stable hunk fixture")
        write_file(
            self.repo,
            "stable.txt",
            "top\n" + "middle\n" * 12 + "changed bottom\n",
        )
        unstaged = ChangeContextCollector(
            self.service, self.limits()
        ).collect(str(self.repo), include_unstaged=True)
        original_id = unstaged.changes[0].hunks[0].change_id

        run_git(self.repo, "add", "stable.txt")
        staged = ChangeContextCollector(
            self.service, self.limits()
        ).collect(str(self.repo), include_unstaged=True)
        self.assertEqual(staged.changes[0].hunks[0].change_id, original_id)

        run_git(self.repo, "reset", "HEAD", "--", "stable.txt")
        write_file(
            self.repo,
            "stable.txt",
            "inserted one\ninserted two\ntop\n"
            + "middle\n" * 12
            + "changed bottom\n",
        )
        shifted = ChangeContextCollector(
            self.service, self.limits()
        ).collect(str(self.repo), include_unstaged=True)
        bottom_hunk = next(
            hunk for hunk in shifted.changes[0].hunks
            if "changed bottom" in hunk.content
        )
        self.assertEqual(bottom_hunk.change_id, original_id)

    def test_snapshot_limits_reject_unsafe_instruction_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "不安全"):
            SnapshotLimits(1, 1, 1, 1, 1, 1, ("../secret.txt",))


if __name__ == "__main__":
    unittest.main()
