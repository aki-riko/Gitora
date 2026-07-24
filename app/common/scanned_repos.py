# coding: utf-8
"""扫描到的 Git 仓库路径缓存。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .logger import get_logger
from .setting import CONFIG_FOLDER


logger = get_logger("ScannedRepos")


class ScannedReposCache:
    """持久化扫描器发现的仓库，并在读取时清理失效记录。"""

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or CONFIG_FOLDER / "scanned_repos.json"
        loaded_repos = self._load()
        self._repos = self._normalize_repos(loaded_repos)
        self._repo_keys = {self._path_key(path) for path in self._repos}
        valid_repos = self._valid_repos(self._repos)
        if valid_repos != loaded_repos:
            self._replace_repos(valid_repos)
            self.save()

    @staticmethod
    def _normalize_path(repo_path: str) -> str:
        return os.path.normpath(repo_path)

    @classmethod
    def _path_key(cls, repo_path: str) -> str:
        return os.path.normcase(cls._normalize_path(repo_path))

    @classmethod
    def _normalize_repos(cls, repos: list[str]) -> list[str]:
        normalized_repos: list[str] = []
        seen: set[str] = set()
        for repo_path in repos:
            if not isinstance(repo_path, str) or not repo_path:
                continue
            normalized_path = cls._normalize_path(repo_path)
            path_key = cls._path_key(normalized_path)
            if path_key in seen:
                continue
            seen.add(path_key)
            normalized_repos.append(normalized_path)
        return normalized_repos

    @classmethod
    def merge_prioritized(
        cls, priority_paths: list[str], fallback_paths: list[str]
    ) -> list[str]:
        """按路径等价规则合并列表；等价项保留优先列表中的记录。"""
        return cls._normalize_repos([*priority_paths, *fallback_paths])

    def _replace_repos(self, repos: list[str]) -> None:
        self._repos = repos
        self._repo_keys = {self._path_key(path) for path in repos}

    @staticmethod
    def _is_repository(repo_path: str) -> bool:
        return (Path(repo_path) / ".git").exists()

    @classmethod
    def _valid_repos(cls, repos: list[str]) -> list[str]:
        return [repo_path for repo_path in repos if cls._is_repository(repo_path)]

    def _load(self) -> list[str]:
        if not self.file_path.exists():
            return []
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                logger.warning("扫描仓库缓存格式无效:根节点必须是对象")
                return []
            repos = data.get("repos", [])
            return repos if isinstance(repos, list) else []
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(f"读取扫描仓库缓存失败: {exc}")
            return []

    def add(self, repo_path: str) -> tuple[str, bool]:
        """添加扫描结果，返回规范化路径及是否新增；写盘由调用方触发。"""
        normalized_path = self._normalize_path(repo_path)
        path_key = self._path_key(normalized_path)
        if path_key in self._repo_keys:
            return normalized_path, False
        self._repos.append(normalized_path)
        self._repo_keys.add(path_key)
        return normalized_path, True

    def get_all(self) -> list[str]:
        valid_repos = self._valid_repos(self._normalize_repos(self._repos))
        if valid_repos != self._repos:
            self._replace_repos(valid_repos)
            self.save()
        return list(self._repos)

    def save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps({"repos": self._repos}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error(f"保存扫描仓库缓存失败: {exc}")
