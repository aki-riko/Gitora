# coding: utf-8
"""扫描到的 Git 仓库路径缓存。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .logger import get_logger
from .setting import CONFIG_FOLDER


logger = get_logger("ScannedRepos")
MAX_SCANNED_REPOSITORIES = 5000

# Win32 GetDriveType 返回值:网络驱动器(含 UNC 共享)
_DRIVE_REMOTE = 4


def _is_remote_path(repo_path: str) -> bool:
    """判断路径是否位于网络位置(映射的网盘或 UNC 共享)。

    ``GetDriveTypeW`` 只读本地挂载表,不访问网络;而 ``Path.exists()`` 会真的去
    探测远端共享,对方断线时能阻塞数十秒。失效校验虽已挪到池线程
    (``prune_missing``),但远端路径连池线程也不该白等——一律不做存在性探测,
    条目保留,真正打开失败时由业务反馈。
    """
    if os.name != "nt":
        return False
    drive, _rest = os.path.splitdrive(repo_path)
    if not drive:
        return False
    if drive.startswith("\\\\"):
        return True
    try:
        import ctypes

        return (
            ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == _DRIVE_REMOTE
        )
    except (AttributeError, OSError):
        return False


class ScannedReposCache:
    """持久化扫描器发现的仓库，并在读取时清理失效记录。"""

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or CONFIG_FOLDER / "scanned_repos.json"
        loaded_repos = self._load()
        self._repos = self._normalize_repos(loaded_repos)
        self._repo_keys = {self._path_key(path) for path in self._repos}
        # 启动路径(GUI 主线程)只做纯内存归一化,绝不做文件系统探测:网络路径的
        # exists() 在远端断开时能阻塞数十秒,曾把应用卡死在启动页(见
        # docs/startup-hang-root-cause.md 的 2026-09-19 复发记录)。失效校验由
        # 扫描任务在池线程里调用 prune_missing 完成。

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
        self._repos = repos[:MAX_SCANNED_REPOSITORIES]
        self._repo_keys = {self._path_key(path) for path in self._repos}

    @staticmethod
    def _is_repository(repo_path: str) -> bool:
        # 远端路径不探测:探测会阻塞(见 _is_remote_path 说明);
        # 条目保留,真正打开失败时由业务给出反馈。
        if _is_remote_path(repo_path):
            return True
        return (Path(repo_path) / ".git").exists()

    @classmethod
    def _valid_repos(cls, repos: list[str]) -> list[str]:
        return [
            repo_path
            for repo_path in repos[:MAX_SCANNED_REPOSITORIES]
            if cls._is_repository(repo_path)
        ]

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
        if len(self._repos) >= MAX_SCANNED_REPOSITORIES:
            return normalized_path, False
        self._repos.append(normalized_path)
        self._repo_keys.add(path_key)
        return normalized_path, True

    def get_all(self) -> list[str]:
        """返回缓存条目;纯内存,不做任何磁盘探测(失效清理见 ``prune_missing``)。"""
        normalized_repos = self._normalize_repos(self._repos)
        if normalized_repos != self._repos:
            self._replace_repos(normalized_repos)
            self.save()
        return list(self._repos[:MAX_SCANNED_REPOSITORIES])

    def prune_missing(self) -> None:
        """剔除磁盘上已不存在的缓存条目并落盘;**只允许池线程调用**。

        本地路径做一次 ``.git`` 存在探测;远端路径不做探测、条目保留
        (见 ``_is_remote_path`` 说明)。
        """
        valid_repos = self._valid_repos(self._repos)
        if valid_repos != self._repos:
            self._replace_repos(valid_repos)
            self.save()

    def save(self) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text(
                json.dumps({"repos": self._repos}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error(f"保存扫描仓库缓存失败: {exc}")
