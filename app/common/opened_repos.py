# coding:utf-8
"""
已打开仓库会话管理

记录“关闭应用时仍然打开着的仓库标签页”，供下次启动完整恢复。
与 recent_repos 的区别：
- recent_repos 是历史访问记录（最多 10 条，只增不减）；
- opened_repos 是当前会话快照（用户关掉某个标签页就从里面移除）。
"""
import json
import os
from pathlib import Path

from .logger import get_logger
from .setting import CONFIG_FOLDER

logger = get_logger("OpenedRepos")


class OpenedReposManager:
    """已打开仓库标签页会话管理器"""

    MAX_OPENED = 32  # 上限，防止异常写入把配置撑爆

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or CONFIG_FOLDER / "opened_repos.json"
        loaded_repos, loaded_active = self._load()
        self._repos = self._normalize_repos(loaded_repos)
        self._active = self._resolve_active(loaded_active)
        if self._repos != loaded_repos or self._active != loaded_active:
            self._save()

    @staticmethod
    def _normalize_path(repo_path: str) -> str:
        """统一为当前系统的原生路径格式。"""
        return os.path.normpath(repo_path)

    @classmethod
    def _path_key(cls, repo_path: str) -> str:
        """生成用于比较的路径键，Windows 下同时忽略大小写和斜杠差异。"""
        return os.path.normcase(cls._normalize_path(repo_path))

    @classmethod
    def _normalize_repos(cls, repos: list[str]) -> list[str]:
        """按原顺序规范化并移除等价路径。"""
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
        return normalized_repos[: cls.MAX_OPENED]

    def _resolve_active(self, active: str) -> str:
        """活动仓库必须是列表成员，否则回退到第一项。"""
        if isinstance(active, str) and active:
            active_key = self._path_key(active)
            for repo_path in self._repos:
                if self._path_key(repo_path) == active_key:
                    return repo_path
        return self._repos[0] if self._repos else ""

    def _load(self) -> tuple[list[str], str]:
        """加载会话快照 -> (仓库列表, 活动仓库)"""
        if not self.file_path.exists():
            return [], ""

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"读取已打开仓库失败: {e}")
            return [], ""

        if not isinstance(data, dict):
            logger.warning(f"已打开仓库配置格式异常: {type(data).__name__}")
            return [], ""

        repos = data.get("repos", [])
        active = data.get("active", "")
        if not isinstance(repos, list):
            logger.warning(f"已打开仓库列表格式异常: {type(repos).__name__}")
            repos = []
        if not isinstance(active, str):
            logger.warning(f"活动仓库格式异常: {type(active).__name__}")
            active = ""
        return repos, active

    def _save(self):
        """保存会话快照"""
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"repos": self._repos, "active": self._active},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"保存已打开仓库失败: {e}")

    def replace(self, repos: list[str], active: str = ""):
        """整体替换会话快照（标签页新增/关闭/排序/切换后调用）。"""
        normalized_repos = self._normalize_repos(list(repos or []))
        if normalized_repos == self._repos:
            normalized_active = self._resolve_active(active)
            if normalized_active == self._active:
                return
            self._active = normalized_active
            self._save()
            return

        self._repos = normalized_repos
        self._active = self._resolve_active(active)
        self._save()

    def get_all(self) -> list[str]:
        """获取仍然存在于磁盘上的已打开仓库；顺带清理失效项。"""
        valid_repos = [
            repo_path for repo_path in self._normalize_repos(self._repos)
            if Path(repo_path).exists()
        ]

        if valid_repos != self._repos:
            self._repos = valid_repos
            self._active = self._resolve_active(self._active)
            self._save()

        return list(self._repos)

    def get_active(self) -> str:
        """获取活动仓库；先经过存在性清理，保证返回值可直接打开。"""
        self.get_all()
        return self._active

    def clear(self):
        """清空会话快照"""
        if not self._repos and not self._active:
            return
        self._repos = []
        self._active = ""
        self._save()


# 全局实例
openedReposManager = OpenedReposManager()
