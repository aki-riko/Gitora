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
        valid_repos = self._valid_repos(self._repos)
        if valid_repos != loaded_repos:
            self._repos = valid_repos
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
            repos = data.get("repos", [])
            return repos if isinstance(repos, list) else []
        except (OSError, ValueError, TypeError) as exc:
            logger.warning(f"读取扫描仓库缓存失败: {exc}")
            return []

    def add(self, repo_path: str) -> tuple[str, bool]:
        """添加扫描结果，返回规范化路径及是否新增；写盘由调用方触发。"""
        normalized_path = self._normalize_path(repo_path)
        path_key = self._path_key(normalized_path)
        if any(self._path_key(path) == path_key for path in self._repos):
            return normalized_path, False
        self._repos.append(normalized_path)
        return normalized_path, True

    def get_all(self) -> list[str]:
        valid_repos = self._valid_repos(self._normalize_repos(self._repos))
        if valid_repos != self._repos:
            self._repos = valid_repos
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
