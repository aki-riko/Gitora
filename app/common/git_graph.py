# coding: utf-8
"""提交图引用解析与稳定轨道布局。"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Sequence


@dataclass(frozen=True)
class CommitRef:
    """提交上的一个可展示 Git 引用。"""

    name: str
    kind: str


@dataclass(frozen=True)
class CommitGraphSegment:
    """一行内从上方轨道到下方轨道的连接段。"""

    from_lane: int
    to_lane: int
    color_index: int
    start_at_node: bool = False
    end_at_node: bool = False


@dataclass(frozen=True)
class CommitGraphRow:
    """单条提交对应的图布局。"""

    node_lane: int
    node_color_index: int
    segments: tuple[CommitGraphSegment, ...]
    header_segments: tuple[CommitGraphSegment, ...]
    lane_count: int


@dataclass(frozen=True)
class _Lane:
    commit_hash: str
    color_index: int


def _normalize_ref(raw: str) -> CommitRef | None:
    value = raw.strip()
    if not value:
        return None
    if value == "HEAD":
        return CommitRef("HEAD", "head")
    if value.startswith("tag: "):
        value = value[len("tag: "):]
    if value.startswith("refs/tags/"):
        return CommitRef(value[len("refs/tags/"):], "tag")
    if value.startswith("refs/heads/"):
        return CommitRef(value[len("refs/heads/"):], "branch")
    if value.startswith("refs/remotes/"):
        name = value[len("refs/remotes/"):]
        return None if name.endswith("/HEAD") else CommitRef(name, "remote")
    return CommitRef(value, "ref")


def parse_commit_refs(decorations: str) -> tuple[CommitRef, ...]:
    """解析 ``git log --decorate=full`` 的 ``%D`` 输出。"""
    refs: list[CommitRef] = []
    seen: set[tuple[str, str]] = set()
    for token in decorations.split(", "):
        values = token.split(" -> ", 1) if " -> " in token else [token]
        for value in values:
            ref = _normalize_ref(value)
            if ref is None or (ref.kind, ref.name) in seen:
                continue
            seen.add((ref.kind, ref.name))
            refs.append(ref)
    return tuple(refs)


def _lane_index(lanes: Sequence[_Lane], commit_hash: str) -> int:
    return next(
        (index for index, lane in enumerate(lanes) if lane.commit_hash == commit_hash),
        -1,
    )


def _insert_parent_lanes(
    lanes: list[_Lane],
    node_lane: int,
    parents: Sequence[str],
    node_color: int,
    next_color: int,
) -> int:
    for parent_index, parent_hash in enumerate(parents):
        if _lane_index(lanes, parent_hash) >= 0:
            continue
        color_index = node_color if parent_index == 0 else next_color
        if parent_index > 0:
            next_color += 1
        insert_at = min(node_lane + parent_index, len(lanes))
        lanes.insert(insert_at, _Lane(parent_hash, color_index))
    return next_color


def _header_segments(lanes: Sequence[_Lane]) -> tuple[CommitGraphSegment, ...]:
    return tuple(
        CommitGraphSegment(index, index, lane.color_index)
        for index, lane in enumerate(lanes)
    )


def _continuation_segments(
    top_lanes: Sequence[_Lane],
    bottom_lanes: Sequence[_Lane],
    node_lane: int,
) -> list[CommitGraphSegment]:
    segments: list[CommitGraphSegment] = []
    for top_index, lane in enumerate(top_lanes):
        if top_index == node_lane:
            continue
        target = _lane_index(bottom_lanes, lane.commit_hash)
        if target >= 0:
            segments.append(
                CommitGraphSegment(top_index, target, lane.color_index)
            )
    return segments


def _node_segments(
    top_lanes: Sequence[_Lane],
    bottom_lanes: Sequence[_Lane],
    node_lane: int,
    parents: Sequence[str],
    node_was_active: bool,
) -> list[CommitGraphSegment]:
    segments: list[CommitGraphSegment] = []
    if node_was_active:
        segments.append(
            CommitGraphSegment(
                node_lane,
                node_lane,
                top_lanes[node_lane].color_index,
                end_at_node=True,
            )
        )
    for parent_hash in dict.fromkeys(parents):
        target = _lane_index(bottom_lanes, parent_hash)
        if target >= 0:
            segments.append(
                CommitGraphSegment(
                    node_lane,
                    target,
                    bottom_lanes[target].color_index,
                    start_at_node=True,
                )
            )
    return segments


def _row_segments(
    top_lanes: Sequence[_Lane],
    bottom_lanes: Sequence[_Lane],
    node_lane: int,
    parents: Sequence[str],
    node_was_active: bool,
) -> tuple[CommitGraphSegment, ...]:
    segments = _continuation_segments(top_lanes, bottom_lanes, node_lane)
    segments.extend(
        _node_segments(
            top_lanes,
            bottom_lanes,
            node_lane,
            parents,
            node_was_active,
        )
    )
    return tuple(segments)


def _activate_node(
    active: list[_Lane], commit_hash: str, next_color: int
) -> tuple[int, bool, int]:
    node_lane = _lane_index(active, commit_hash)
    if node_lane >= 0:
        return node_lane, True, next_color
    active.append(_Lane(commit_hash, next_color))
    return len(active) - 1, False, next_color + 1


def _build_graph_row(
    active: list[_Lane],
    commit_hash: str,
    parents: Sequence[str],
    next_color: int,
) -> tuple[CommitGraphRow, list[_Lane], int]:
    header_lanes = tuple(active)
    node_lane, node_was_active, next_color = _activate_node(
        active, commit_hash, next_color
    )
    top_lanes = tuple(active)
    node_color = top_lanes[node_lane].color_index
    bottom_lanes = list(top_lanes)
    bottom_lanes.pop(node_lane)
    next_color = _insert_parent_lanes(
        bottom_lanes, node_lane, parents, node_color, next_color
    )
    row = CommitGraphRow(
        node_lane=node_lane,
        node_color_index=node_color,
        segments=_row_segments(
            top_lanes, bottom_lanes, node_lane, parents, node_was_active
        ),
        header_segments=_header_segments(header_lanes),
        lane_count=max(1, len(top_lanes), len(bottom_lanes)),
    )
    return row, bottom_lanes, next_color


def layout_commit_graph(
    topology: Iterable[tuple[str, Sequence[str]]],
) -> tuple[CommitGraphRow, ...]:
    """按从新到旧的拓扑序生成稳定轨道；同一前缀的既有行不会被后页改写。"""
    active: list[_Lane] = []
    rows: list[CommitGraphRow] = []
    next_color = 0
    maximum_lanes = 1
    for commit_hash, parents in topology:
        row, active, next_color = _build_graph_row(
            active, commit_hash, parents, next_color
        )
        maximum_lanes = max(maximum_lanes, row.lane_count)
        rows.append(row)
    return tuple(replace(row, lane_count=maximum_lanes) for row in rows)
