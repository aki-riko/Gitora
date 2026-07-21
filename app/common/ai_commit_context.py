# coding: utf-8
"""AI 提交规划器的只读 Git 变更快照收集器。"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .ai_commit_models import ChangeSnapshot, FileChangeSnapshot, HunkChange
from .git_service import DiffFile, DiffHunk, FileChange, FileStatus, GitService


class SnapshotCollectionError(RuntimeError):
    """无法从真实仓库建立可信快照。"""


@dataclass(frozen=True)
class SnapshotLimits:
    max_total_chars: int
    max_file_chars: int
    max_untracked_chars: int
    max_files: int
    history_count: int
    instruction_files: tuple[str, ...]

    def __post_init__(self) -> None:
        numeric = (
            self.max_total_chars, self.max_file_chars,
            self.max_untracked_chars, self.max_files, self.history_count,
        )
        if any(value <= 0 for value in numeric):
            raise ValueError("快照限制必须为正整数")
        for name in self.instruction_files:
            if not name or Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError(f"不安全的规范文件路径: {name}")


class ChangeContextCollector:
    """读取 Git 状态并建立稳定、可校验、不会修改仓库的快照。"""

    def __init__(self, git_service: GitService, limits: SnapshotLimits):
        self._git = git_service
        self._limits = limits

    def collect(self, repo_path: str, include_unstaged: bool) -> ChangeSnapshot:
        repo = os.path.realpath(repo_path)
        if not GitService._is_git_work_tree_path(repo):
            raise SnapshotCollectionError("不是有效的 Git 工作树")

        status = self._git.get_status_at(repo)
        staged_ok, staged_diff, staged_error = self._git.get_raw_diff_at(repo, True)
        unstaged_ok, unstaged_diff, unstaged_error = self._git.get_raw_diff_at(repo, False)
        if not staged_ok:
            raise SnapshotCollectionError(staged_error or "读取暂存区差异失败")
        if include_unstaged and not unstaged_ok:
            raise SnapshotCollectionError(unstaged_error or "读取工作区差异失败")
        full_unstaged_diff = unstaged_diff
        if not include_unstaged:
            unstaged_diff = ""

        head = self._git.get_head_at(repo)
        branch = self._git.get_current_branch_at(repo)
        relevant_status = [change for change in status if include_unstaged or change.staged]
        warnings: list[str] = []
        complete = True
        if len(relevant_status) > self._limits.max_files:
            relevant_status = relevant_status[:self._limits.max_files]
            warnings.append("变更文件数超过配置上限，快照未包含全部文件")
            complete = False

        parsed = {
            True: self._index_diff(GitService.parse_unified_diff(staged_diff)),
            False: self._index_diff(GitService.parse_unified_diff(unstaged_diff)),
        }
        full_state = self._workspace_state_payload(
            head, branch, status, staged_diff, full_unstaged_diff, repo
        )
        workspace_fingerprint = self._digest_json(full_state)
        repository_token = hashlib.sha256(
            os.path.normcase(repo).encode("utf-8", "replace")
        ).hexdigest()

        remaining = self._limits.max_total_chars
        changes: list[FileChangeSnapshot] = []
        for status_change in relevant_status:
            change, consumed = self._build_change(
                repo, status_change, parsed[status_change.staged], remaining
            )
            changes.append(change)
            remaining -= consumed
            if change.truncated:
                complete = False
                warnings.append(f"{change.path} 的内容超过配置上限，已截断")

        titles = tuple(
            commit.message for commit in self._git.get_log_at(
                repo, count=self._limits.history_count, fast_mode=True
            )
        )
        instructions, instruction_warnings = self._read_instructions(repo)
        warnings.extend(instruction_warnings)
        if instruction_warnings:
            complete = False

        snapshot_payload = {
            "workspace_fingerprint": workspace_fingerprint,
            "include_unstaged": include_unstaged,
            "changes": [self._change_identity_payload(item) for item in changes],
            "recent_titles": titles,
            "instructions": instructions,
        }
        snapshot_id = self._digest_json(snapshot_payload)
        return ChangeSnapshot(
            snapshot_id=snapshot_id,
            workspace_fingerprint=workspace_fingerprint,
            repository_token=repository_token,
            head=head,
            branch=branch,
            include_unstaged=include_unstaged,
            complete=complete,
            changes=tuple(changes),
            recent_titles=titles,
            instructions=tuple(instructions),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def workspace_fingerprint(self, repo_path: str) -> str:
        """重新读取工作区，供执行前判断计划是否过期。"""
        repo = os.path.realpath(repo_path)
        status = self._git.get_status_at(repo)
        staged_ok, staged_diff, staged_error = self._git.get_raw_diff_at(repo, True)
        unstaged_ok, unstaged_diff, unstaged_error = self._git.get_raw_diff_at(repo, False)
        if not staged_ok or not unstaged_ok:
            raise SnapshotCollectionError(staged_error or unstaged_error or "读取差异失败")
        return self._digest_json(self._workspace_state_payload(
            self._git.get_head_at(repo), self._git.get_current_branch_at(repo),
            status, staged_diff, unstaged_diff, repo,
        ))

    @staticmethod
    def _index_diff(files: list[DiffFile]) -> dict[str, DiffFile]:
        result: dict[str, DiffFile] = {}
        for file_diff in files:
            for path in (file_diff.path, file_diff.old_path, file_diff.new_path):
                if path:
                    result[path] = file_diff
        return result

    def _build_change(
        self,
        repo: str,
        status_change: FileChange,
        diff_index: dict[str, DiffFile],
        remaining: int,
    ) -> tuple[FileChangeSnapshot, int]:
        file_diff = diff_index.get(status_change.path)
        if status_change.status == FileStatus.UNTRACKED:
            full_content, binary, unsupported = self._read_untracked(repo, status_change.path)
            raw = full_content
            old_path = ""
            new_path = status_change.path
            additions = 0 if binary else len(full_content.splitlines())
            deletions = 0
            hunks: tuple[HunkChange, ...] = ()
        else:
            raw = file_diff.raw if file_diff else ""
            binary = "Binary files " in raw or "GIT binary patch" in raw
            unsupported = "二进制改动" if binary else ""
            old_path = file_diff.old_path if file_diff else status_change.path
            new_path = file_diff.new_path if file_diff else status_change.path
            additions = file_diff.additions if file_diff else 0
            deletions = file_diff.deletions if file_diff else 0
            hunks = self._build_hunks(status_change, file_diff)

        allowance = max(0, min(self._limits.max_file_chars, remaining))
        truncated = unsupported == "内容不完整" or len(raw) > allowance
        visible = raw[:allowance]
        if truncated:
            hunks = ()
        identity = {
            "path": status_change.path,
            "old_path": old_path,
            "new_path": new_path,
            "status": status_change.status.value,
            "staged": status_change.staged,
            "raw_sha256": hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest(),
        }
        change_id = "file_" + self._digest_json(identity)[:24]
        if truncated and not unsupported:
            unsupported = "内容不完整"
        return FileChangeSnapshot(
            change_id=change_id,
            path=status_change.path,
            old_path=old_path,
            new_path=new_path,
            status=status_change.status.value,
            staged=status_change.staged,
            binary=binary,
            truncated=truncated,
            unsupported_reason=unsupported,
            additions=additions,
            deletions=deletions,
            patch=visible,
            hunks=hunks,
        ), len(visible)

    def _build_hunks(
        self, status_change: FileChange, file_diff: DiffFile | None
    ) -> tuple[HunkChange, ...]:
        if not file_diff:
            return ()
        result: list[HunkChange] = []
        for hunk in file_diff.hunks:
            content = self._hunk_content(hunk)
            identity = {
                "path": status_change.path,
                "staged": status_change.staged,
                "header": hunk.header,
                "content": content,
            }
            result.append(HunkChange(
                change_id="hunk_" + self._digest_json(identity)[:24],
                header=hunk.header,
                old_start=hunk.old_start,
                old_count=hunk.old_count,
                new_start=hunk.new_start,
                new_count=hunk.new_count,
                additions=sum(line.kind == "added" for line in hunk.lines),
                deletions=sum(line.kind == "deleted" for line in hunk.lines),
                content=content,
            ))
        return tuple(result)

    @staticmethod
    def _hunk_content(hunk: DiffHunk) -> str:
        prefixes = {"added": "+", "deleted": "-", "context": " ", "meta": "\\"}
        lines = [hunk.header]
        lines.extend(prefixes.get(line.kind, "") + line.text for line in hunk.lines)
        return "\n".join(lines) + "\n"

    def _read_untracked(self, repo: str, relative_path: str) -> tuple[str, bool, str]:
        lexical_target = os.path.abspath(os.path.join(repo, relative_path))
        if not self._is_within_repo(repo, lexical_target):
            return "", False, "路径越界"
        if os.path.islink(lexical_target):
            try:
                return os.readlink(lexical_target), False, "符号链接不支持自动执行"
            except OSError as exc:
                return "", False, f"无法读取符号链接（{type(exc).__name__}）"
        target = os.path.realpath(lexical_target)
        if not self._is_within_repo(repo, target):
            return "", False, "路径越界"
        try:
            data = Path(target).read_bytes()
        except OSError as exc:
            return "", False, f"无法读取未跟踪文件（{type(exc).__name__}）"
        if b"\x00" in data:
            return "", True, "二进制未跟踪文件"
        text = data.decode("utf-8", "replace")
        if len(text) > self._limits.max_untracked_chars:
            return text[:self._limits.max_untracked_chars], False, "内容不完整"
        return text, False, ""

    def _read_instructions(self, repo: str) -> tuple[list[tuple[str, str]], list[str]]:
        result: list[tuple[str, str]] = []
        warnings: list[str] = []
        for name in self._limits.instruction_files:
            target = os.path.realpath(os.path.join(repo, name))
            if not self._is_within_repo(repo, target):
                warnings.append(f"规范文件路径越界: {name}")
                continue
            if not os.path.isfile(target):
                continue
            try:
                content = Path(target).read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                warnings.append(f"无法读取规范文件 {name}（{type(exc).__name__}）")
                continue
            if len(content) > self._limits.max_file_chars:
                content = content[:self._limits.max_file_chars]
                warnings.append(f"规范文件 {name} 超过配置上限，已截断")
            result.append((name, content))
        return result, warnings

    def _workspace_state_payload(
        self,
        head: str,
        branch: str,
        status: list[FileChange],
        staged_diff: str,
        unstaged_diff: str,
        repo: str,
    ) -> dict[str, object]:
        untracked = {}
        for change in status:
            if change.status != FileStatus.UNTRACKED:
                continue
            untracked[change.path] = {
                "sha256": self._hash_untracked(repo, change.path),
            }
        return {
            "head": head,
            "branch": branch,
            "status": [
                [change.path, change.status.value, change.staged] for change in status
            ],
            "staged_sha256": hashlib.sha256(staged_diff.encode("utf-8", "replace")).hexdigest(),
            "unstaged_sha256": hashlib.sha256(unstaged_diff.encode("utf-8", "replace")).hexdigest(),
            "untracked": untracked,
        }

    @staticmethod
    def _change_identity_payload(change: FileChangeSnapshot) -> dict[str, object]:
        return {
            "change_id": change.change_id,
            "path": change.path,
            "staged": change.staged,
            "truncated": change.truncated,
            "unsupported_reason": change.unsupported_reason,
            "hunk_ids": [hunk.change_id for hunk in change.hunks],
        }

    @staticmethod
    def _is_within_repo(repo: str, target: str) -> bool:
        try:
            return os.path.normcase(os.path.commonpath([repo, target])) == os.path.normcase(repo)
        except ValueError:
            return False

    @staticmethod
    def _hash_file(path: str) -> str:
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(64 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            return f"unreadable:{type(exc).__name__}"
        return digest.hexdigest()

    def _hash_untracked(self, repo: str, relative_path: str) -> str:
        lexical_target = os.path.abspath(os.path.join(repo, relative_path))
        if not self._is_within_repo(repo, lexical_target):
            return "unsafe:path"
        if os.path.islink(lexical_target):
            try:
                link_target = os.readlink(lexical_target)
            except OSError as exc:
                return f"unreadable-link:{type(exc).__name__}"
            return hashlib.sha256(
                ("symlink\x00" + link_target).encode("utf-8", "replace")
            ).hexdigest()
        target = os.path.realpath(lexical_target)
        if not self._is_within_repo(repo, target):
            return "unsafe:resolved-path"
        return self._hash_file(target)

    @staticmethod
    def _digest_json(value: object) -> str:
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()
