# coding: utf-8
"""使用真实 Git 分叉与合并历史验证提交图数据。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from app.common.git_service import GitService
from app_qml.backend.git_bridge import _commit_to_dict
from tests.git_test_utils import commit_all, init_repo, run_git, write_file


def _graph_signature(commit) -> tuple:
    row = commit.graph
    assert row is not None
    return (
        commit.hash,
        row.node_lane,
        row.node_color_index,
        row.segments,
        row.header_segments,
    )


def _build_branched_repo(root: Path) -> tuple[Path, dict[str, str]]:
    repo = init_repo(root / "repo")
    write_file(repo, "root.txt", "root\n")
    initial = commit_all(repo, "initial")

    run_git(repo, "branch", "feature")
    write_file(repo, "main.txt", "main\n")
    main_work = commit_all(repo, "main work")

    run_git(repo, "checkout", "feature")
    write_file(repo, "feature.txt", "feature\n")
    feature_work = commit_all(repo, "feature work")
    run_git(repo, "checkout", "master")
    run_git(repo, "merge", "--no-ff", "feature", "-m", "merge feature")
    merge = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    run_git(repo, "tag", "v-graph", merge)
    run_git(repo, "update-ref", "refs/remotes/origin/master", merge)

    run_git(repo, "checkout", "-b", "side", initial)
    write_file(repo, "side.txt", "side\n")
    side = commit_all(repo, "side work")
    run_git(repo, "checkout", "master")
    return repo, {
        "initial": initial,
        "main": main_work,
        "feature": feature_work,
        "merge": merge,
        "side": side,
    }


def test_graph_log_includes_all_refs_merge_parents_and_stable_pages() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo, hashes = _build_branched_repo(Path(temp_dir))
        service = GitService()

        full = service.get_graph_log_at(str(repo), count=20)
        by_hash = {commit.hash: commit for commit in full}
        assert set(by_hash) == set(hashes.values())

        merge = by_hash[hashes["merge"]]
        assert merge.parents == [hashes["main"], hashes["feature"]]
        assert {(ref.name, ref.kind) for ref in merge.refs} >= {
            ("HEAD", "head"),
            ("master", "branch"),
            ("v-graph", "tag"),
            ("origin/master", "remote"),
        }
        assert merge.graph is not None
        assert len(
            [segment for segment in merge.graph.segments if segment.start_at_node]
        ) == 2

        first_page = service.get_graph_log_at(str(repo), count=2, skip=0)
        second_page = service.get_graph_log_at(str(repo), count=2, skip=2)
        assert [commit.hash for commit in first_page + second_page] == [
            commit.hash for commit in full[:4]
        ]
        assert [_graph_signature(commit) for commit in first_page] == [
            _graph_signature(commit) for commit in full[:2]
        ]
        assert [_graph_signature(commit) for commit in second_page] == [
            _graph_signature(commit) for commit in full[2:4]
        ]

        payload = _commit_to_dict(merge)
        assert payload["parents"] == merge.parents
        assert payload["graph"]["laneCount"] >= 2
        assert len(payload["graph"]["segments"]) >= 2
        assert payload["graphHeader"]["segments"] is not None
