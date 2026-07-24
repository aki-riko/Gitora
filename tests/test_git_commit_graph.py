# coding: utf-8
"""使用真实 Git 分叉与合并历史验证提交图数据。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from app.common.git_service import GitService
from app_qml.backend.git_bridge import _commit_to_dict
from tests.git_test_utils import build_branched_repo


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


def _assert_merge_payload(merge, hashes: dict[str, str]) -> None:
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
    payload = _commit_to_dict(merge)
    assert payload["parents"] == merge.parents
    assert payload["graph"]["laneCount"] >= 2
    assert len(payload["graph"]["segments"]) >= 2
    assert payload["graphHeader"]["segments"] is not None


def _assert_stable_pages(
    service: GitService, repo: Path, full: list, include_all_refs: bool
) -> None:
    first_page = service.get_graph_log_at(
        str(repo), count=2, skip=0, include_all_refs=include_all_refs
    )
    second_page = service.get_graph_log_at(
        str(repo), count=2, skip=2, include_all_refs=include_all_refs
    )
    assert [commit.hash for commit in first_page + second_page] == [
        commit.hash for commit in full[:4]
    ]
    assert [_graph_signature(commit) for commit in first_page] == [
        _graph_signature(commit) for commit in full[:2]
    ]
    assert [_graph_signature(commit) for commit in second_page] == [
        _graph_signature(commit) for commit in full[2:4]
    ]


def test_graph_log_supports_current_head_and_all_refs_with_stable_pages() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        repo, hashes = build_branched_repo(Path(temp_dir))
        service = GitService()

        current = service.get_graph_log_at(str(repo), count=20)
        current_by_hash = {commit.hash: commit for commit in current}
        assert set(current_by_hash) == set(hashes.values()) - {hashes["side"]}
        _assert_merge_payload(current_by_hash[hashes["merge"]], hashes)
        _assert_stable_pages(service, repo, current, include_all_refs=False)

        all_refs = service.get_graph_log_at(
            str(repo), count=20, include_all_refs=True
        )
        all_by_hash = {commit.hash: commit for commit in all_refs}
        assert set(all_by_hash) == set(hashes.values())
        assert {(ref.name, ref.kind) for ref in all_by_hash[hashes["side"]].refs} >= {
            ("side", "branch")
        }
        _assert_stable_pages(service, repo, all_refs, include_all_refs=True)
