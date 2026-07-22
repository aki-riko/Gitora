# coding: utf-8
"""提交图布局纯逻辑测试。"""
from app.common.git_graph import layout_commit_graph, parse_commit_refs


def test_parse_commit_refs_normalizes_full_decorations() -> None:
    refs = parse_commit_refs(
        "HEAD -> refs/heads/master, tag: refs/tags/v1.0.0, "
        "refs/remotes/origin/master, refs/remotes/origin/HEAD"
    )

    assert [(ref.name, ref.kind) for ref in refs] == [
        ("HEAD", "head"),
        ("master", "branch"),
        ("v1.0.0", "tag"),
        ("origin/master", "remote"),
    ]


def test_linear_graph_starts_at_tip_and_ends_at_root() -> None:
    rows = layout_commit_graph(
        [("commit-c", ["commit-b"]), ("commit-b", ["commit-a"]), ("commit-a", [])]
    )

    assert rows[0].header_segments == ()
    assert len(rows[0].segments) == 1
    assert rows[0].segments[0].start_at_node is True
    assert rows[0].segments[0].end_at_node is False
    assert any(segment.end_at_node for segment in rows[1].segments)
    assert any(segment.start_at_node for segment in rows[1].segments)
    assert len(rows[2].segments) == 1
    assert rows[2].segments[0].end_at_node is True


def test_merge_graph_allocates_second_parent_lane_and_keeps_prefix_stable() -> None:
    topology = [
        ("merge", ["main-work", "feature-work"]),
        ("main-work", ["root"]),
        ("feature-work", ["root"]),
        ("root", []),
    ]
    full = layout_commit_graph(topology)
    prefix = layout_commit_graph(topology[:2])

    outgoing = [segment for segment in full[0].segments if segment.start_at_node]
    assert len(outgoing) == 2
    assert {segment.to_lane for segment in outgoing} == {0, 1}
    assert full[0].lane_count == 2
    assert full[0].segments == prefix[0].segments
    assert full[1].segments == prefix[1].segments
