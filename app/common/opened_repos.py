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
import tempfile
import threading
from pathlib import Path

from .logger import get_logger
from .setting import CONFIG_FOLDER

logger = get_logger("OpenedRepos")


class OpenedReposManager:
    """已打开仓库标签页会话管理器

    线程安全：写盘由后台线程池发起，可能有多次快照并发到达，因此所有读写都
    在同一把锁内完成。并发之外还要防乱序——线程池不保证完成顺序，旧快照后
    到会覆盖新快照，所以 ``replace`` 接受调用方在主线程分配的单调 ``sequence``，
    迟到的旧快照直接丢弃。
    """

    MAX_OPENED = 32  # 上限，防止异常写入把配置撑爆

    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or CONFIG_FOLDER / "opened_repos.json"
        self._lock = threading.RLock()
        self._applied_sequence = -1
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
        """活动仓库必须是当前列表成员，否则回退到第一项。"""
        return self._resolve_active_in(self._repos, active)

    @classmethod
    def _resolve_active_in(cls, repos: list[str], active: str) -> str:
        """在给定列表里解析活动仓库，避免依赖尚未提交的实例状态。"""
        if isinstance(active, str) and active:
            active_key = cls._path_key(active)
            for repo_path in repos:
                if cls._path_key(repo_path) == active_key:
                    return repo_path
        return repos[0] if repos else ""

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
        """原子保存会话快照。

        直接以 ``w`` 打开会先截断再写：写一半崩溃就留下坏 JSON，下次启动读成
        空快照，等于把所有标签页丢干净——正是本功能要防的事故。所以先写同目录
        临时文件再 ``os.replace`` 原子替换。
        """
        payload = json.dumps(
            {"repos": self._repos, "active": self._active},
            ensure_ascii=False,
            indent=2,
        )
        temp_path = None
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                dir=str(self.file_path.parent),
                prefix=f".{self.file_path.name}.",
                suffix=".tmp",
            )
            temp_path = Path(temp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, self.file_path)
            temp_path = None
        except Exception as e:
            logger.error(f"保存已打开仓库失败: {e}")
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError as e:
                    logger.warning(f"清理已打开仓库临时文件失败: {e}")

    def replace(self, repos: list[str], active: str = "", sequence: int | None = None):
        """整体替换会话快照（标签页新增/关闭/排序/切换后调用）。

        ``sequence`` 由调用方在主线程单调分配；小于已应用值的快照视为线程池
        乱序导致的迟到结果，直接丢弃，避免旧状态覆盖新状态。
        """
        with self._lock:
            if sequence is not None:
                if sequence <= self._applied_sequence:
                    logger.debug(
                        f"丢弃迟到的已打开仓库快照: seq={sequence} "
                        f"已应用={self._applied_sequence}"
                    )
                    return
                self._applied_sequence = sequence

            normalized_repos = self._normalize_repos(list(repos or []))
            normalized_active = self._resolve_active_in(normalized_repos, active)
            if (normalized_repos == self._repos
                    and normalized_active == self._active):
                return

            self._repos = normalized_repos
            self._active = normalized_active
            self._save()

    def get_all(self) -> list[str]:
        """获取仍然存在于磁盘上的已打开仓库；顺带清理失效项。

        会对每个路径做一次 ``exists()``；调用方必须放后台线程。
        """
        with self._lock:
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
        with self._lock:
            self.get_all()
            return self._active

    def get_snapshot(self) -> tuple[list[str], str]:
        """一次拿到 (仓库列表, 活动仓库)，只做一轮存在性检查。

        分别调 ``get_all`` + ``get_active`` 会把 ``exists()`` 跑两遍；启动路径
        上这是白花的磁盘时间。
        """
        with self._lock:
            repos = self.get_all()
            return repos, self._active

    def clear(self):
        """清空会话快照"""
        with self._lock:
            if not self._repos and not self._active:
                return
            self._repos = []
            self._active = ""
            self._save()


# 全局实例
openedReposManager = OpenedReposManager()
