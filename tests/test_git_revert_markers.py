# coding: utf-8
import tempfile
import unittest
from pathlib import Path

from app.common.git_service import CommitInfo, GitService
from app_qml.backend.git_bridge import _commit_to_dict

from git_test_utils import commit_all, init_repo, run_git, write_file


class GitRevertMarkerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_real_revert_marks_original_across_pagination_and_search(self) -> None:
        repo = init_repo(self.root / "repo")
        write_file(repo, "tracked.txt", "original\n")
        original = commit_all(repo, "original change")
        write_file(repo, "later.txt", "later\n")
        commit_all(repo, "later change")

        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo), emit_status=False))
        self.assertEqual(service.get_log(count=1, skip=1)[0].reverted_by, "")

        run_git(repo, "revert", "--no-edit", original)
        reverting = run_git(repo, "rev-parse", "HEAD").stdout.strip()

        paged_original = service.get_log(count=1, skip=2)[0]
        self.assertEqual(paged_original.hash, original)
        self.assertEqual(paged_original.reverted_by, reverting)

        search_results = service.search_commits("original change", "message", 20)
        searched_by_hash = {commit.hash: commit for commit in search_results}
        self.assertIn(reverting, searched_by_hash)
        self.assertEqual(searched_by_hash[original].reverted_by, reverting)

    def test_revert_like_subject_without_standard_body_does_not_mark(self) -> None:
        repo = init_repo(self.root / "subject-only")
        write_file(repo, "tracked.txt", "original\n")
        original = commit_all(repo, "original change")
        write_file(repo, "other.txt", "other\n")
        commit_all(repo, 'Revert "original change"')

        service = GitService()
        self.assertTrue(service.set_repo_path(str(repo), emit_status=False))
        by_hash = {commit.hash: commit for commit in service.get_log(10)}

        self.assertEqual(by_hash[original].reverted_by, "")

    def test_bridge_exposes_reverting_hash_to_qml(self) -> None:
        commit = CommitInfo(
            "a" * 40,
            "a" * 7,
            "author",
            "author@example.invalid",
            "2026-07-22 19:06",
            "change",
            reverted_by="b" * 40,
        )

        self.assertEqual(_commit_to_dict(commit)["revertedBy"], "b" * 40)


class HistoryRevertMarkerContractTest(unittest.TestCase):
    def test_history_marks_reverted_commit_in_list_and_detail(self) -> None:
        qml_path = (
            Path(__file__).resolve().parents[1]
            / "app_qml"
            / "qml"
            / "views"
            / "HistoryView.qml"
        )
        source = qml_path.read_text(encoding="utf-8")

        self.assertIn('var isReverted = !!c.revertedBy', source)
        self.assertIn('(isReverted ? " · 已撤销" : "")', source)
        self.assertIn('"strikeOut": isReverted', source)
        self.assertIn('status: Fluent.Enums.statusLevel.warning', source)
        self.assertIn('"已撤销 · " + root.selectedCommit.revertedBy.substring(0, 7)', source)


if __name__ == "__main__":
    unittest.main()
