# coding:utf-8
"""
最近仓库管理
"""
import json
import os
from pathlib import Path

from .logger import get_logger

logger = get_logger("RecentRepos")
from .setting import CONFIG_FOLDER


class RecentReposManager:
    """最近仓库管理器"""
    
    MAX_RECENT = 10  # 最多保存10个
    
    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or CONFIG_FOLDER / "recent_repos.json"
        loaded_repos = self._load()
        self._repos = self._normalize_repos(loaded_repos)
        if self._repos != loaded_repos:
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
        normalized_repos = []
        seen = set()
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
    
    def _load(self) -> list[str]:
        """加载最近仓库列表"""
        if not self.file_path.exists():
            return []
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('repos', [])
        except Exception as e:
            logger.warning(f"读取最近仓库失败: {e}")
            return []
    
    def _save(self):
        """保存最近仓库列表"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump({'repos': self._repos}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存最近仓库失败: {e}")
    
    def add(self, repo_path: str):
        """添加仓库到最近列表"""
        normalized_path = self._normalize_path(repo_path)
        path_key = self._path_key(normalized_path)

        # 移除所有等价写法（例如 Windows 下的正/反斜杠路径）
        self._repos = [
            existing_path for existing_path in self._repos
            if self._path_key(existing_path) != path_key
        ]

        # 添加到列表开头
        self._repos.insert(0, normalized_path)
        
        # 限制数量
        if len(self._repos) > self.MAX_RECENT:
            self._repos = self._repos[:self.MAX_RECENT]
        
        self._save()
    
    def remove(self, repo_path: str):
        """从最近列表移除"""
        path_key = self._path_key(repo_path)
        remaining_repos = [
            existing_path for existing_path in self._repos
            if self._path_key(existing_path) != path_key
        ]
        if remaining_repos != self._repos:
            self._repos = remaining_repos
            self._save()
    
    def get_all(self) -> list[str]:
        """获取所有最近仓库"""
        # 过滤不存在的目录，并清理旧配置中的等价路径
        valid_repos = [
            repo_path for repo_path in self._normalize_repos(self._repos)
            if Path(repo_path).exists()
        ]
        
        # 如果有无效的，更新列表
        if len(valid_repos) != len(self._repos):
            self._repos = valid_repos
            self._save()
        
        return self._repos
    
    def clear(self):
        """清空最近列表"""
        self._repos = []
        self._save()


# 全局实例
recentReposManager = RecentReposManager()
