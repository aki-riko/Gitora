# coding:utf-8
"""
最近仓库管理
"""
import json
from pathlib import Path
from .setting import CONFIG_FOLDER


class RecentReposManager:
    """最近仓库管理器"""
    
    MAX_RECENT = 10  # 最多保存10个
    
    def __init__(self):
        self.file_path = CONFIG_FOLDER / "recent_repos.json"
        self._repos = self._load()
    
    def _load(self) -> list[str]:
        """加载最近仓库列表"""
        if not self.file_path.exists():
            return []
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('repos', [])
        except Exception:
            return []
    
    def _save(self):
        """保存最近仓库列表"""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump({'repos': self._repos}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def add(self, repo_path: str):
        """添加仓库到最近列表"""
        # 移除已存在的（避免重复）
        if repo_path in self._repos:
            self._repos.remove(repo_path)
        
        # 添加到列表开头
        self._repos.insert(0, repo_path)
        
        # 限制数量
        if len(self._repos) > self.MAX_RECENT:
            self._repos = self._repos[:self.MAX_RECENT]
        
        self._save()
    
    def remove(self, repo_path: str):
        """从最近列表移除"""
        if repo_path in self._repos:
            self._repos.remove(repo_path)
            self._save()
    
    def get_all(self) -> list[str]:
        """获取所有最近仓库"""
        # 过滤不存在的目录
        valid_repos = [r for r in self._repos if Path(r).exists()]
        
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
