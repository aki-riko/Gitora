# coding:utf-8
"""
Git服务层 - 封装所有Git命令操作
提供异步执行和错误处理
"""
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QMutexLocker


class FileStatus(Enum):
    """文件状态枚举"""
    UNTRACKED = "?"       # 未跟踪
    MODIFIED = "M"        # 已修改
    ADDED = "A"           # 已添加
    DELETED = "D"         # 已删除
    RENAMED = "R"         # 重命名
    COPIED = "C"          # 复制
    UNMERGED = "U"        # 冲突
    IGNORED = "!"         # 忽略


@dataclass
class FileChange:
    """文件变更信息"""
    path: str
    status: FileStatus
    staged: bool = False  # 是否在暂存区

    @property
    def status_text(self) -> str:
        """状态文本"""
        status_map = {
            FileStatus.UNTRACKED: "未跟踪",
            FileStatus.MODIFIED: "已修改",
            FileStatus.ADDED: "新文件",
            FileStatus.DELETED: "已删除",
            FileStatus.RENAMED: "重命名",
            FileStatus.COPIED: "复制",
            FileStatus.UNMERGED: "冲突",
            FileStatus.IGNORED: "已忽略",
        }
        return status_map.get(self.status, "未知")


@dataclass
class CommitInfo:
    """提交信息"""
    hash: str
    short_hash: str
    author: str
    email: str
    date: str
    message: str
    branch: str = ""


@dataclass
class BranchInfo:
    """分支信息"""
    name: str
    is_current: bool
    is_remote: bool
    tracking: str = ""
    ahead: int = 0
    behind: int = 0


@dataclass
class ConflictInfo:
    """冲突信息"""
    path: str
    ours_content: str = ""    # 我们的版本内容
    theirs_content: str = ""  # 他们的版本内容
    base_content: str = ""    # 基础版本内容
    has_conflict_markers: bool = False  # 是否有冲突标记


class GitWorker(QThread):
    """Git命令异步执行线程"""
    finished = Signal(bool, str, str)  # success, stdout, stderr

    def __init__(self, cmd: list[str], cwd: str, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = cwd

    def run(self):
        try:
            result = subprocess.run(
                self.cmd,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            self.finished.emit(
                result.returncode == 0,
                result.stdout,
                result.stderr
            )
        except Exception as e:
            self.finished.emit(False, "", str(e))


class GitService(QObject):
    """Git服务 - 提供所有Git操作接口"""

    # 信号定义
    statusChanged = Signal()                    # 状态变更
    operationStarted = Signal(str)              # 操作开始
    operationFinished = Signal(bool, str)       # 操作完成(成功/失败, 消息)
    progressUpdated = Signal(int, str)          # 进度更新(百分比, 消息)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repo_path: Optional[str] = None
        self._mutex = QMutex()
        self._workers: list[GitWorker] = []

    @property
    def repo_path(self) -> Optional[str]:
        return self._repo_path

    def set_repo_path(self, path: str) -> bool:
        """设置仓库路径"""
        if not path or not os.path.isdir(path):
            return False

        git_dir = os.path.join(path, '.git')
        if not os.path.isdir(git_dir):
            return False

        self._repo_path = path
        self.statusChanged.emit()
        return True

    def _run_git_sync(self, args: list[str]) -> tuple[bool, str, str]:
        """同步执行Git命令"""
        if not self._repo_path:
            return False, "", "未设置仓库路径"

        cmd = ['git'] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self._repo_path,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return result.returncode == 0, result.stdout, result.stderr
        except FileNotFoundError:
            return False, "", "Git未安装或不在PATH中"
        except Exception as e:
            return False, "", str(e)

    def _run_git_async(self, args: list[str], callback: Callable[[bool, str, str], None]):
        """异步执行Git命令"""
        if not self._repo_path:
            callback(False, "", "未设置仓库路径")
            return

        cmd = ['git'] + args
        worker = GitWorker(cmd, self._repo_path, self)
        worker.finished.connect(callback)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _cleanup_worker(self, worker: GitWorker):
        """清理完成的worker"""
        if worker in self._workers:
            self._workers.remove(worker)

    # ==================== 状态查询 ====================

    def get_status(self) -> list[FileChange]:
        """获取工作区状态"""
        success, stdout, stderr = self._run_git_sync(['status', '--porcelain=v1', '-uall'])
        if not success:
            return []

        changes = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue

            # 解析状态: XY PATH
            index_status = line[0]   # 暂存区状态
            work_status = line[1]    # 工作区状态
            path = line[3:].strip()

            # 处理重命名情况
            if ' -> ' in path:
                path = path.split(' -> ')[1]

            # 确定文件状态
            if index_status == '?' and work_status == '?':
                changes.append(FileChange(path, FileStatus.UNTRACKED, False))
            else:
                # 暂存区有变更
                if index_status != ' ' and index_status != '?':
                    status = self._parse_status_char(index_status)
                    changes.append(FileChange(path, status, True))

                # 工作区有变更（未暂存）
                if work_status != ' ' and work_status != '?':
                    status = self._parse_status_char(work_status)
                    # 检查是否已存在暂存版本
                    existing = next((c for c in changes if c.path == path and c.staged), None)
                    if not existing:
                        changes.append(FileChange(path, status, False))

        return changes

    def _parse_status_char(self, char: str) -> FileStatus:
        """解析状态字符"""
        status_map = {
            'M': FileStatus.MODIFIED,
            'A': FileStatus.ADDED,
            'D': FileStatus.DELETED,
            'R': FileStatus.RENAMED,
            'C': FileStatus.COPIED,
            'U': FileStatus.UNMERGED,
            '?': FileStatus.UNTRACKED,
            '!': FileStatus.IGNORED,
        }
        return status_map.get(char, FileStatus.MODIFIED)

    def get_current_branch(self) -> str:
        """获取当前分支名"""
        success, stdout, _ = self._run_git_sync(['rev-parse', '--abbrev-ref', 'HEAD'])
        return stdout.strip() if success else ""

    def get_branches(self) -> list[BranchInfo]:
        """获取所有分支"""
        branches = []

        # 本地分支
        success, stdout, _ = self._run_git_sync(['branch', '-vv'])
        if success:
            for line in stdout.strip().split('\n'):
                if not line:
                    continue

                is_current = line.startswith('*')
                line = line[2:].strip()

                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    tracking = ""
                    ahead = behind = 0

                    # 解析追踪信息
                    if '[' in line:
                        start = line.index('[')
                        end = line.index(']')
                        tracking_info = line[start+1:end]
                        if ':' in tracking_info:
                            tracking = tracking_info.split(':')[0]

                    branches.append(BranchInfo(
                        name=name,
                        is_current=is_current,
                        is_remote=False,
                        tracking=tracking,
                        ahead=ahead,
                        behind=behind
                    ))

        # 远程分支
        success, stdout, _ = self._run_git_sync(['branch', '-r'])
        if success:
            for line in stdout.strip().split('\n'):
                line = line.strip()
                if not line or '->' in line:
                    continue

                branches.append(BranchInfo(
                    name=line,
                    is_current=False,
                    is_remote=True
                ))

        return branches

    def get_log(self, count: int = 50, skip: int = 0) -> list[CommitInfo]:
        """获取提交历史
        
        Args:
            count: 获取数量
            skip: 跳过前N条记录（用于分页）
        """
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log',
            f'-{count}',
            f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M'
        ]
        if skip > 0:
            cmd.append(f'--skip={skip}')

        success, stdout, _ = self._run_git_sync(cmd)

        if not success:
            return []

        commits = []
        current_branch = self.get_current_branch()

        for line in stdout.strip().split('\n'):
            if not line:
                continue

            parts = line.split('|', 5)
            if len(parts) == 6:
                commits.append(CommitInfo(
                    hash=parts[0],
                    short_hash=parts[1],
                    author=parts[2],
                    email=parts[3],
                    date=parts[4],
                    message=parts[5],
                    branch=current_branch
                ))

        return commits

    def search_commits(self, query: str, search_type: str = "all", count: int = 50) -> list[CommitInfo]:
        """搜索提交记录
        
        Args:
            query: 搜索关键词
            search_type: 搜索类型（"all"=全部, "message"=提交信息, "author"=作者）
            count: 最大返回数量
        """
        if not query or not query.strip():
            return self.get_log(count=count)
        
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log',
            f'-{count}',
            f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M'
        ]
        
        # 根据搜索类型添加过滤条件
        if search_type == "message":
            cmd.append(f'--grep={query}')
        elif search_type == "author":
            cmd.append(f'--author={query}')
        else:
            # 全部搜索：消息或作者（使用正则表达式OR逻辑）
            # Git默认是OR逻辑，分别添加--grep和--author即可
            cmd.extend([f'--grep={query}', f'--author={query}'])
        
        success, stdout, _ = self._run_git_sync(cmd)
        
        if not success:
            return []
        
        commits = []
        current_branch = self.get_current_branch()
        
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split('|', 5)
            if len(parts) == 6:
                commits.append(CommitInfo(
                    hash=parts[0],
                    short_hash=parts[1],
                    author=parts[2],
                    email=parts[3],
                    date=parts[4],
                    message=parts[5],
                    branch=current_branch
                ))
        
        return commits

    def get_diff(self, file_path: str, staged: bool = False) -> str:
        """获取文件差异"""
        args = ['diff']
        if staged:
            args.append('--cached')
        args.append('--')
        args.append(file_path)

        success, stdout, _ = self._run_git_sync(args)
        return stdout if success else ""

    def get_remotes(self) -> list[str]:
        """获取远程仓库列表"""
        success, stdout, _ = self._run_git_sync(['remote'])
        return stdout.strip().split('\n') if success and stdout.strip() else []

    # ==================== 暂存操作 ====================

    def stage_file(self, file_path: str) -> bool:
        """暂存单个文件"""
        success, _, stderr = self._run_git_sync(['add', '--', file_path])
        if success:
            self.statusChanged.emit()
        return success

    def stage_all(self) -> bool:
        """暂存所有变更"""
        success, _, stderr = self._run_git_sync(['add', '-A'])
        if success:
            self.statusChanged.emit()
        return success

    def unstage_file(self, file_path: str) -> bool:
        """取消暂存单个文件"""
        success, _, stderr = self._run_git_sync(['reset', 'HEAD', '--', file_path])
        if success:
            self.statusChanged.emit()
        return success

    def unstage_all(self) -> bool:
        """取消暂存所有文件"""
        success, _, stderr = self._run_git_sync(['reset', 'HEAD'])
        if success:
            self.statusChanged.emit()
        return success

    def discard_file(self, file_path: str) -> bool:
        """放弃文件修改"""
        # 先检查文件状态
        changes = self.get_status()
        file_change = next((c for c in changes if c.path == file_path), None)

        if not file_change:
            return False

        if file_change.status == FileStatus.UNTRACKED:
            # 删除未跟踪文件
            try:
                full_path = os.path.join(self._repo_path, file_path)
                os.remove(full_path)
                self.statusChanged.emit()
                return True
            except Exception:
                return False
        else:
            # 恢复已跟踪文件
            success, _, _ = self._run_git_sync(['checkout', '--', file_path])
            if success:
                self.statusChanged.emit()
            return success

    # ==================== 提交操作 ====================

    def commit(self, message: str) -> tuple[bool, str]:
        """提交暂存的变更"""
        if not message.strip():
            return False, "提交信息不能为空"

        success, stdout, stderr = self._run_git_sync(['commit', '-m', message])
        if success:
            self.statusChanged.emit()
            return True, "提交成功"
        return False, stderr or "提交失败"

    def amend_commit(self, message: str) -> tuple[bool, str]:
        """修改最后一次提交"""
        success, stdout, stderr = self._run_git_sync(['commit', '--amend', '-m', message])
        if success:
            self.statusChanged.emit()
            return True, "修改提交成功"
        return False, stderr or "修改提交失败"

    # ==================== 推送/拉取操作 ====================

    def push(self, remote: str = "origin", branch: str = "", callback: Callable[[bool, str], None] = None):
        """推送到远程（异步）"""
        self.operationStarted.emit("正在推送...")

        args = ['push', remote]
        if branch:
            args.append(branch)

        def on_finished(success: bool, stdout: str, stderr: str):
            msg = "推送成功" if success else (stderr or "推送失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)

        self._run_git_async(args, on_finished)

    def push_with_upstream(self, remote: str = "origin", branch: str = "", callback: Callable[[bool, str], None] = None):
        """推送并设置上游分支（异步）"""
        self.operationStarted.emit("正在推送...")

        if not branch:
            branch = self.get_current_branch()

        args = ['push', '-u', remote, branch]

        def on_finished(success: bool, stdout: str, stderr: str):
            msg = "推送成功" if success else (stderr or "推送失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)

        self._run_git_async(args, on_finished)

    def pull(self, remote: str = "origin", branch: str = "", callback: Callable[[bool, str], None] = None):
        """拉取远程变更（异步）"""
        self.operationStarted.emit("正在拉取...")

        args = ['pull', remote]
        if branch:
            args.append(branch)

        def on_finished(success: bool, stdout: str, stderr: str):
            if success:
                self.statusChanged.emit()
            msg = "拉取成功" if success else (stderr or "拉取失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)

        self._run_git_async(args, on_finished)

    def fetch(self, remote: str = "origin", callback: Callable[[bool, str], None] = None):
        """获取远程更新（异步）"""
        self.operationStarted.emit("正在获取远程更新...")

        def on_finished(success: bool, stdout: str, stderr: str):
            msg = "获取成功" if success else (stderr or "获取失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)

        self._run_git_async(['fetch', remote], on_finished)

    # ==================== 分支操作 ====================

    def checkout_branch(self, branch: str) -> tuple[bool, str]:
        """切换分支"""
        success, stdout, stderr = self._run_git_sync(['checkout', branch])
        if success:
            self.statusChanged.emit()
            return True, f"已切换到分支 {branch}"
        return False, stderr or "切换分支失败"

    def create_branch(self, branch: str, checkout: bool = True) -> tuple[bool, str]:
        """创建分支"""
        if checkout:
            success, stdout, stderr = self._run_git_sync(['checkout', '-b', branch])
        else:
            success, stdout, stderr = self._run_git_sync(['branch', branch])

        if success:
            self.statusChanged.emit()
            return True, f"已创建分支 {branch}"
        return False, stderr or "创建分支失败"

    def delete_branch(self, branch: str, force: bool = False) -> tuple[bool, str]:
        """删除分支"""
        args = ['branch', '-D' if force else '-d', branch]
        success, stdout, stderr = self._run_git_sync(args)
        if success:
            self.statusChanged.emit()
            return True, f"已删除分支 {branch}"
        return False, stderr or "删除分支失败"

    def merge_branch(self, branch: str) -> tuple[bool, str]:
        """合并分支"""
        success, stdout, stderr = self._run_git_sync(['merge', branch])
        if success:
            self.statusChanged.emit()
            return True, f"已合并分支 {branch}"
        return False, stderr or "合并分支失败"

    # ==================== 回滚操作（危险） ====================

    def revert_commit(self, commit_hash: str) -> tuple[bool, str]:
        """撤销指定提交（创建新提交来撤销，安全）
        
        使用 git revert，会创建一个新的提交来撤销指定提交的更改。
        这是安全的操作，不会修改历史。
        """
        success, stdout, stderr = self._run_git_sync(['revert', '--no-edit', commit_hash])
        if success:
            self.statusChanged.emit()
            return True, f"已撤销提交 {commit_hash[:7]}（创建了新的撤销提交）"
        return False, stderr or "撤销提交失败"

    def reset_to_commit(self, commit_hash: str, mode: str = "mixed") -> tuple[bool, str]:
        """回滚到指定提交（危险操作，会修改历史）
        
        Args:
            commit_hash: 目标提交的hash
            mode: 回滚模式
                - "soft": 保留工作区和暂存区的修改
                - "mixed": 保留工作区修改，清空暂存区（默认）
                - "hard": 完全回滚，丢弃所有修改（最危险）
        
        警告: 这会修改Git历史，如果已推送到远程，可能导致问题！
        """
        if mode not in ("soft", "mixed", "hard"):
            return False, f"无效的回滚模式: {mode}"
        
        success, stdout, stderr = self._run_git_sync(['reset', f'--{mode}', commit_hash])
        if success:
            self.statusChanged.emit()
            mode_desc = {
                "soft": "保留所有修改在暂存区",
                "mixed": "保留工作区修改",
                "hard": "丢弃所有修改"
            }
            return True, f"已回滚到 {commit_hash[:7]}（{mode_desc[mode]}）"
        return False, stderr or "回滚失败"

    def get_commit_count_after(self, commit_hash: str) -> int:
        """获取指定提交之后的提交数量"""
        success, stdout, stderr = self._run_git_sync([
            'rev-list', '--count', f'{commit_hash}..HEAD'
        ])
        if success:
            try:
                return int(stdout.strip())
            except ValueError:
                return -1
        return -1

    # ==================== 一键操作 ====================

    def quick_commit_push(
        self,
        message: str,
        callback: Callable[[bool, str], None] = None
    ):
        """一键操作：暂存 + 提交 + 推送"""
        self.operationStarted.emit("正在执行一键提交推送...")
        self.progressUpdated.emit(0, "暂存所有变更...")

        # 步骤1：暂存所有
        if not self.stage_all():
            msg = "暂存失败"
            self.operationFinished.emit(False, msg)
            if callback:
                callback(False, msg)
            return

        self.progressUpdated.emit(33, "提交变更...")

        # 步骤2：提交
        success, commit_msg = self.commit(message)
        if not success:
            self.operationFinished.emit(False, commit_msg)
            if callback:
                callback(False, commit_msg)
            return

        self.progressUpdated.emit(66, "推送到远程...")

        # 步骤3：推送
        def on_push_finished(success: bool, push_msg: str):
            if success:
                self.progressUpdated.emit(100, "完成")
                self.operationFinished.emit(True, "一键提交推送成功")
            else:
                self.operationFinished.emit(False, f"推送失败: {push_msg}")

            if callback:
                callback(success, push_msg if not success else "一键提交推送成功")

        # 检查是否有远程仓库
        remotes = self.get_remotes()
        if not remotes:
            msg = "提交成功，但没有配置远程仓库"
            self.operationFinished.emit(True, msg)
            if callback:
                callback(True, msg)
            return

        self.push_with_upstream(callback=on_push_finished)

    # ==================== 冲突处理 ====================

    def get_conflicts(self) -> list[ConflictInfo]:
        """获取冲突文件列表"""
        conflicts = []
        
        # 获取所有未合并的文件（U状态）
        changes = self.get_status()
        conflict_files = [c for c in changes if c.status == FileStatus.UNMERGED]
        
        for file_change in conflict_files:
            conflict = ConflictInfo(path=file_change.path)
            
            # 读取文件内容检查是否有冲突标记
            try:
                full_path = os.path.join(self._repo_path, file_change.path)
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if '<<<<<<<' in content and '>>>>>>>' in content:
                        conflict.has_conflict_markers = True
            except Exception:
                pass
            
            conflicts.append(conflict)
        
        return conflicts

    def resolve_conflict_with_ours(self, file_path: str) -> tuple[bool, str]:
        """使用我们的版本解决冲突"""
        success, stdout, stderr = self._run_git_sync(['checkout', '--ours', '--', file_path])
        if success:
            # 标记为已解决（添加到暂存区）
            self.stage_file(file_path)
            return True, f"已使用我们的版本解决冲突: {file_path}"
        return False, stderr or "解决冲突失败"

    def resolve_conflict_with_theirs(self, file_path: str) -> tuple[bool, str]:
        """使用他们的版本解决冲突"""
        success, stdout, stderr = self._run_git_sync(['checkout', '--theirs', '--', file_path])
        if success:
            # 标记为已解决（添加到暂存区）
            self.stage_file(file_path)
            return True, f"已使用他们的版本解决冲突: {file_path}"
        return False, stderr or "解决冲突失败"

    def abort_merge(self) -> tuple[bool, str]:
        """中止合并操作"""
        success, stdout, stderr = self._run_git_sync(['merge', '--abort'])
        if success:
            self.statusChanged.emit()
            return True, "已中止合并"
        return False, stderr or "中止合并失败"

    def is_merging(self) -> bool:
        """检查是否正在合并"""
        if not self._repo_path:
            return False
        merge_head = os.path.join(self._repo_path, '.git', 'MERGE_HEAD')
        return os.path.exists(merge_head)

    # ==================== Stash暂存 ====================

    def stash_save(self, message: str = "") -> tuple[bool, str]:
        """暂存当前变更到stash"""
        args = ['stash', 'push']
        if message:
            args.extend(['-m', message])
        
        success, stdout, stderr = self._run_git_sync(args)
        if success:
            self.statusChanged.emit()
            return True, "已暂存变更到stash"
        return False, stderr or "暂存失败"

    def stash_list(self) -> list[tuple[str, str]]:
        """获取stash列表
        
        Returns:
            list of (stash_id, message)
        """
        success, stdout, stderr = self._run_git_sync(['stash', 'list'])
        if not success:
            return []
        
        stashes = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            # 格式: stash@{0}: WIP on branch: message
            if ':' in line:
                stash_id = line.split(':')[0].strip()
                message = ':'.join(line.split(':')[1:]).strip()
                stashes.append((stash_id, message))
        
        return stashes

    def stash_pop(self, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """恢复stash并删除"""
        success, stdout, stderr = self._run_git_sync(['stash', 'pop', stash_id])
        if success:
            self.statusChanged.emit()
            return True, f"已恢复stash: {stash_id}"
        return False, stderr or "恢复stash失败"

    def stash_apply(self, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """恢复stash但不删除"""
        success, stdout, stderr = self._run_git_sync(['stash', 'apply', stash_id])
        if success:
            self.statusChanged.emit()
            return True, f"已应用stash: {stash_id}"
        return False, stderr or "应用stash失败"

    def stash_drop(self, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """删除指定stash"""
        success, stdout, stderr = self._run_git_sync(['stash', 'drop', stash_id])
        if success:
            return True, f"已删除stash: {stash_id}"
        return False, stderr or "删除stash失败"

    def stash_clear(self) -> tuple[bool, str]:
        """清空所有stash"""
        success, stdout, stderr = self._run_git_sync(['stash', 'clear'])
        if success:
            return True, "已清空所有stash"
        return False, stderr or "清空stash失败"

    # ==================== 文件历史 ====================

    def get_file_history(self, file_path: str, count: int = 50) -> list[CommitInfo]:
        """获取指定文件的提交历史"""
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log',
            f'-{count}',
            f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M',
            '--follow',  # 跟踪文件重命名
            '--',
            file_path
        ]
        
        success, stdout, _ = self._run_git_sync(cmd)
        if not success:
            return []
        
        commits = []
        current_branch = self.get_current_branch()
        
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            
            parts = line.split('|', 5)
            if len(parts) == 6:
                commits.append(CommitInfo(
                    hash=parts[0],
                    short_hash=parts[1],
                    author=parts[2],
                    email=parts[3],
                    date=parts[4],
                    message=parts[5],
                    branch=current_branch
                ))
        
        return commits

    def get_file_content_at_commit(self, file_path: str, commit_hash: str) -> str:
        """获取文件在指定提交的内容"""
        success, stdout, stderr = self._run_git_sync(['show', f'{commit_hash}:{file_path}'])
        return stdout if success else ""

    def diff_file_between_commits(self, file_path: str, commit1: str, commit2: str) -> str:
        """对比文件在两个提交之间的差异"""
        success, stdout, _ = self._run_git_sync(['diff', commit1, commit2, '--', file_path])
        return stdout if success else ""


# 全局单例
gitService = GitService()
