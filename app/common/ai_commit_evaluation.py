# coding: utf-8
"""AI 提交规划器的真实历史回放与硬指标记录。"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from .ai_commit_context import ChangeContextCollector, SnapshotLimits
from .ai_commit_models import (
    ChangeSnapshot,
    CommitPlan,
    CommitPlanValidator,
    PlannerRequest,
)
from .ai_commit_patch import TemporaryIndexValidator
from .ai_commit_provider import ModelProvider
from .git_service import GitService


class EvaluationError(RuntimeError):
    """历史样本不足、临时回放失败或结果无法落盘。"""


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    base_commit: str
    target_commits: tuple[str, ...]
    tip_commit: str
    expected_titles: tuple[str, ...]
    changed_paths: tuple[str, ...]
    categories: tuple[str, ...]
    additions: int
    deletions: int
    contains_binary: bool
    combined_diff_chars: int
    combined_diff_sha256: str

    def __post_init__(self) -> None:
        commit_pattern = re.compile(r"[0-9a-f]{40,64}")
        commits = (self.base_commit, self.tip_commit, *self.target_commits)
        if not self.target_commits or any(
            not commit_pattern.fullmatch(commit) for commit in commits
        ):
            raise EvaluationError("回放清单包含无效提交哈希")
        if self.tip_commit != self.target_commits[-1]:
            raise EvaluationError("回放 tip 与目标提交不一致")
        if len(self.expected_titles) != len(self.target_commits):
            raise EvaluationError("回放标题数量与目标提交不一致")
        if not re.fullmatch(r"case-[0-9]{3}-[0-9a-f]{10}", self.case_id):
            raise EvaluationError("回放样本标识格式无效")
        if not re.fullmatch(r"[0-9a-f]{64}", self.combined_diff_sha256):
            raise EvaluationError("回放差异摘要格式无效")
        if any("\0" in path or Path(path).is_absolute() for path in self.changed_paths):
            raise EvaluationError("回放清单包含不安全路径")

    def to_mapping(self) -> dict:
        payload = asdict(self)
        for key in (
            "target_commits", "expected_titles", "changed_paths", "categories"
        ):
            payload[key] = list(payload[key])
        return payload

    @classmethod
    def from_mapping(cls, data: dict) -> "ReplayCase":
        return cls(
            case_id=str(data["case_id"]),
            base_commit=str(data["base_commit"]),
            target_commits=tuple(data["target_commits"]),
            tip_commit=str(data["tip_commit"]),
            expected_titles=tuple(data["expected_titles"]),
            changed_paths=tuple(data["changed_paths"]),
            categories=tuple(data["categories"]),
            additions=int(data["additions"]),
            deletions=int(data["deletions"]),
            contains_binary=bool(data["contains_binary"]),
            combined_diff_chars=int(data["combined_diff_chars"]),
            combined_diff_sha256=str(data["combined_diff_sha256"]),
        )


@dataclass(frozen=True)
class EvaluationRecord:
    case_id: str
    provider_kind: str
    provider_id: str
    model: str
    started_at: str
    total_latency_ms: int
    provider_latency_ms: int
    status: str
    failure_type: str
    protocol_valid: bool
    coverage_percent: int
    duplicate_count: int
    patch_valid: bool

    def to_mapping(self) -> dict:
        return asdict(self)


class HistoryReplayBuilder:
    """从真实 first-parent 历史选取不重叠连续窗口。"""

    def __init__(self, repo_path: str, timeout_seconds: int):
        self._repo = os.path.realpath(repo_path)
        self._timeout = timeout_seconds

    def build(self, count: int, commits_per_case: int = 2) -> list[ReplayCase]:
        if count <= 0 or commits_per_case <= 0:
            raise EvaluationError("样本数和每组提交数必须为正整数")
        commits = self._lines(["rev-list", "--first-parent", "--reverse", "HEAD"])
        if len(commits) < count * commits_per_case + 1:
            raise EvaluationError("first-parent 历史不足，无法生成指定数量样本")
        cases: list[ReplayCase] = []
        cursor = len(commits)
        for index in range(count):
            start = cursor - commits_per_case
            targets = tuple(commits[start:cursor])
            cases.append(self._build_case(index + 1, commits[start - 1], targets))
            cursor = start
        return cases

    def _build_case(
        self, index: int, base_commit: str, targets: tuple[str, ...]
    ) -> ReplayCase:
        tip = targets[-1]
        diff = self._run(["diff", "--binary", base_commit, tip])
        paths = tuple(filter(None, self._run(
            ["diff", "--name-only", "-z", base_commit, tip]
        ).split("\0")))
        additions, deletions, binary = self._numstat(base_commit, tip)
        digest = hashlib.sha256(diff.encode("utf-8", "replace")).hexdigest()
        return ReplayCase(
            case_id=f"case-{index:03d}-{tip[:10]}",
            base_commit=base_commit,
            target_commits=targets,
            tip_commit=tip,
            expected_titles=tuple(self._title(commit) for commit in targets),
            changed_paths=paths,
            categories=self._categories(paths),
            additions=additions,
            deletions=deletions,
            contains_binary=binary,
            combined_diff_chars=len(diff),
            combined_diff_sha256=digest,
        )

    def _numstat(self, base_commit: str, tip_commit: str) -> tuple[int, int, bool]:
        additions = deletions = 0
        binary = False
        for line in self._lines(["diff", "--numstat", base_commit, tip_commit]):
            fields = line.split("\t", 2)
            if len(fields) < 2:
                continue
            if fields[0] == "-" or fields[1] == "-":
                binary = True
                continue
            additions += int(fields[0])
            deletions += int(fields[1])
        return additions, deletions, binary

    def _title(self, commit: str) -> str:
        return self._run(["show", "-s", "--format=%s", commit]).strip()

    def _lines(self, args: list[str]) -> list[str]:
        return [line for line in self._run(args).splitlines() if line]

    def _run(self, args: list[str]) -> str:
        return _run_git(self._repo, args, self._timeout)

    @staticmethod
    def _categories(paths: Sequence[str]) -> tuple[str, ...]:
        result: set[str] = set()
        for path in paths:
            normalized = path.replace("\\", "/").lower()
            suffix = Path(path).suffix.lower()
            if suffix == ".py":
                result.add("python")
            if suffix == ".qml":
                result.add("qml")
            if suffix in {".md", ".rst", ".txt"}:
                result.add("docs")
            if "/test" in f"/{normalized}" or normalized.startswith("tests/"):
                result.add("tests")
        return tuple(sorted(result or {"other"}))


@contextmanager
def replay_workspace(
    source_repo: str,
    case: ReplayCase,
    limits: SnapshotLimits,
    timeout_seconds: int,
) -> Iterator[tuple[str, GitService, ChangeSnapshot]]:
    """在临时克隆内构造 base→tip 的真实未提交工作区。"""
    with tempfile.TemporaryDirectory(prefix="gitora-ai-replay-") as temp_dir:
        workspace = Path(temp_dir) / "repo"
        _run_git(temp_dir, [
            "clone", "--quiet", "--no-hardlinks", os.path.realpath(source_repo),
            str(workspace),
        ], timeout_seconds)
        _run_git(
            str(workspace),
            ["checkout", "--quiet", "--detach", case.tip_commit],
            timeout_seconds,
        )
        _run_git(
            str(workspace),
            ["reset", "--mixed", "--quiet", case.base_commit],
            timeout_seconds,
        )
        service = GitService()
        if not service.set_repo_path(str(workspace), emit_status=False):
            raise EvaluationError("无法打开历史回放临时仓库")
        snapshot = ChangeContextCollector(service, limits).collect(
            str(workspace), include_unstaged=True
        )
        yield str(workspace), service, snapshot


class EvaluationRunner:
    """调用给定提供方并记录协议、覆盖、重复和补丁硬指标。"""

    def __init__(
        self,
        source_repo: str,
        limits: SnapshotLimits,
        timeout_seconds: int,
    ):
        self._repo = source_repo
        self._limits = limits
        self._timeout = timeout_seconds

    def run_case(
        self,
        case: ReplayCase,
        provider: ModelProvider,
        provider_kind: str,
        model: str,
    ) -> EvaluationRecord:
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.monotonic()
        provider_latency_ms = 0
        try:
            hard_metrics, provider_latency_ms = self._evaluate(case, provider)
            failure_type = self._hard_failure_type(hard_metrics)
            status = "failed" if failure_type else "passed"
        except Exception as exc:  # noqa: BLE001
            hard_metrics = (False, 0, 0, False)
            status, failure_type = "failed", type(exc).__name__
        total_latency_ms = round((time.monotonic() - started) * 1000)
        return EvaluationRecord(
            case.case_id, provider_kind, provider.provider_id, model,
            started_at, total_latency_ms, provider_latency_ms,
            status, failure_type, *hard_metrics,
        )

    @staticmethod
    def _hard_failure_type(metrics: tuple[bool, int, int, bool]) -> str:
        protocol_valid, coverage, duplicates, patch_valid = metrics
        if not protocol_valid:
            return "plan_validation"
        if coverage != 100:
            return "coverage"
        if duplicates:
            return "duplicate_assignment"
        if not patch_valid:
            return "patch_validation"
        return ""

    def _evaluate(
        self, case: ReplayCase, provider: ModelProvider
    ) -> tuple[tuple[bool, int, int, bool], int]:
        with replay_workspace(
            self._repo, case, self._limits, self._timeout
        ) as replay:
            repo_path, service, snapshot = replay
            request = PlannerRequest(snapshot, "plan", "hunk", True)
            provider_started = time.monotonic()
            raw_plan = provider.generate_plan(request)
            provider_latency_ms = round(
                (time.monotonic() - provider_started) * 1000
            )
            plan = CommitPlan.from_mapping(raw_plan)
            validation = CommitPlanValidator().validate(plan, snapshot, "hunk")
            expected = set(snapshot.expected_ids("hunk"))
            if not expected:
                raise EvaluationError("历史回放样本没有可评测改动")
            assigned = [item for group in plan.groups for item in group.change_ids]
            coverage = round(len(set(assigned) & expected) * 100 / len(expected))
            duplicates = len(assigned) - len(set(assigned))
            patch_valid = False
            if validation.valid and validation.executable:
                TemporaryIndexValidator(service).validate(
                    repo_path, snapshot, plan, validation,
                    self._limits, self._timeout,
                )
                patch_valid = True
            metrics = validation.valid, coverage, duplicates, patch_valid
            return metrics, provider_latency_ms


def write_case_manifest(path: Path, cases: Sequence[ReplayCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(case.to_mapping(), ensure_ascii=False, sort_keys=True) + "\n"
        for case in cases
    )
    path.write_text(content, encoding="utf-8")


def read_case_manifest(path: Path) -> list[ReplayCase]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        return [ReplayCase.from_mapping(json.loads(line)) for line in lines if line]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise EvaluationError("无法读取历史回放清单") from exc


def write_manual_template(path: Path, cases: Sequence[ReplayCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id", "provider_kind", "model", "status", "failure_type",
        "total_latency_ms", "provider_latency_ms", "protocol_valid",
        "coverage_percent", "duplicate_count", "patch_valid",
        "title_score_1_5", "grouping_score_1_5",
        "style_score_1_5", "accepted_without_regroup", "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            for provider_kind in ("local", "remote"):
                writer.writerow({
                    "case_id": case.case_id,
                    "provider_kind": provider_kind,
                    "status": "not_run",
                })


def write_evaluation_records(
    path: Path, records: Sequence[EvaluationRecord]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(record.to_mapping(), ensure_ascii=False, sort_keys=True) + "\n"
        for record in records
    )
    path.write_text(content, encoding="utf-8")


def _run_git(repo_path: str, args: list[str], timeout_seconds: int) -> str:
    try:
        result = subprocess.run(
            ["git", "--literal-pathspecs", "-c", "core.quotepath=false", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvaluationError(f"Git 历史回放失败（{type(exc).__name__}）") from exc
    if result.returncode != 0:
        raise EvaluationError((result.stderr or result.stdout).strip()[-1000:])
    return result.stdout
