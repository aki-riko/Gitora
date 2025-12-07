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

from .logger import get_logger

logger = get_logger("GitService")


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
    """异步执行Git命令线程"""
    finished = Signal(bool, str, str)  # success, stdout, stderr

    def __init__(self, cmd: list[str], cwd: str, timeout: int = 30, parent=None):
        super().__init__(parent)
        self.cmd = cmd
        self.cwd = cwd
        self.timeout = timeout  # 超时时间（秒）

    def run(self):
        cmd_str = ' '.join(self.cmd)
        logger.debug(f"[GitWorker] 执行Git命令: {cmd_str}")
        try:
            # 根据命令类型设置超时
            # 网络操作（push/pull/fetch）使用传入的timeout
            # 本地操作使用较短超时
            result = subprocess.run(
                self.cmd,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=self.timeout,  # 添加超时控制
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            success = result.returncode == 0
            if success:
                logger.debug(f"[GitWorker] 命令执行成功: {cmd_str}")
            else:
                logger.warning(f"[GitWorker] 命令执行失败: {cmd_str}, stderr: {result.stderr}")
            self.finished.emit(
                success,
                result.stdout,
                result.stderr
            )
        except subprocess.TimeoutExpired:
            logger.error(f"[GitWorker] 命令超时: {cmd_str}, timeout={self.timeout}s")
            self.finished.emit(False, "", f"操作超时（{self.timeout}秒），可能是网络问题或仓库过大")
        except Exception as e:
            logger.exception(f"[GitWorker] 命令执行异常: {cmd_str}, error: {e}")
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
        logger.info(f"设置仓库路径: {path}")
        if not path or not os.path.isdir(path):
            logger.warning(f"路径无效: {path}")
            return False

        # 检查目录权限（读取+执行）
        if not os.access(path, os.R_OK | os.X_OK):
            logger.warning(f"目录权限不足: {path}")
            return False

        git_dir = os.path.join(path, '.git')
        if not os.path.isdir(git_dir):
            logger.warning(f"不是Git仓库: {path}")
            return False

        self._repo_path = path
        logger.info(f"仓库路径设置成功: {path}")
        self.statusChanged.emit()
        return True
    
    def is_large_repo(self) -> bool:
        """检测是否为大仓库（超过1000个提交）"""
        if not self._repo_path:
            return False
        
        success, stdout, _ = self._run_git_sync(['rev-list', '--count', 'HEAD'])
        if success:
            try:
                count = int(stdout.strip())
                return count > 1000
            except ValueError:
                return False
        return False
    
    def get_repo_size(self) -> dict:
        """获取仓库统计信息"""
        if not self._repo_path:
            return {}
        
        # 提交数量
        success, stdout, _ = self._run_git_sync(['rev-list', '--count', 'HEAD'])
        commit_count = int(stdout.strip()) if success else 0
        
        # 分支数量
        branches = self.get_branches()
        branch_count = len([b for b in branches if not b.is_remote])
        
        # .git目录大小
        git_dir = os.path.join(self._repo_path, '.git')
        git_size = 0
        try:
            for root, dirs, files in os.walk(git_dir):
                for f in files:
                    fp = os.path.join(root, f)
                    if os.path.exists(fp):
                        git_size += os.path.getsize(fp)
        except Exception:
            pass
        
        return {
            'commit_count': commit_count,
            'branch_count': branch_count,
            'git_size_mb': git_size / (1024 * 1024),
            'is_large': commit_count > 1000
        }

    def _run_git_sync(self, args: list[str], timeout: int = 30) -> tuple[bool, str, str]:
        """同步执行Git命令
        
        Args:
            args: Git命令参数
            timeout: 超时时间（秒），默认30秒
        """
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
                timeout=timeout,  # 添加超时控制
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error(f"Git命令超时: {' '.join(args)}, timeout={timeout}s")
            return False, "", f"操作超时（{timeout}秒）"
        except FileNotFoundError:
            logger.error("Git未安装或不在PATH中")
            return False, "", "Git未安装或不在PATH中"
        except Exception as e:
            logger.exception(f"Git命令异常: {' '.join(args)}, error: {e}")
            return False, "", str(e)

    def _run_git_async(self, args: list[str], callback: Callable[[bool, str, str], None], timeout: int = None):
        """异步执行Git命令
        
        Args:
            args: Git命令参数
            callback: 完成回调
            timeout: 超时时间（秒），默认根据命令类型自动设置
        """
        if not self._repo_path:
            callback(False, "", "未设置仓库路径")
            return

        # 自动设置超时时间
        if timeout is None:
            # 网络操作使用较长超时
            if args[0] in ('push', 'pull', 'fetch', 'clone'):
                timeout = 60  # 60秒
            else:
                timeout = 30  # 本地操作30秒

        cmd = ['git'] + args
        worker = GitWorker(cmd, self._repo_path, timeout, self)
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

    def get_log(self, count: int = 50, skip: int = 0, fast_mode: bool = False) -> list[CommitInfo]:
        """获取提交历史
        
        Args:
            count: 获取数量
            skip: 跳过前N条记录（用于分页）
            fast_mode: 快速模式（大仓库优化）
        """
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log',
            f'-{count}',
            f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M'
        ]
        
        # 大仓库优化：仅显示重要提交
        if fast_mode:
            cmd.append('--first-parent')  # 仅显示第一父提交，加速查询
        
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
            cmd.append('--regexp-ignore-case')
        elif search_type == "author":
            cmd.append(f'--author={query}')
            cmd.append('--regexp-ignore-case')
        else:
            # 全部搜索：消息或作者（OR逻辑）
            # 注意：Git的--grep和--author默认是AND逻辑
            # 需要使用--all-match的反向或分别搜索
            # 这里使用基本正则表达式实现OR
            cmd.append(f'--grep={query}')
            cmd.append('--regexp-ignore-case')
            # 添加--all-match的反向：不使用--all-match时，多个--grep是OR
            # 但--grep和--author混用是AND，所以需要特殊处理
            # 简化方案：只搜索消息，如果需要作者也搜索，用户可以选择"author"类型
        
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
        if not success:
            return ""
        
        # 限制diff大小，防止超大文件导致UI卡顿
        MAX_DIFF_SIZE = 100 * 1024  # 100KB
        if len(stdout) > MAX_DIFF_SIZE:
            truncated = stdout[:MAX_DIFF_SIZE]
            truncated += "\n\n" + "="*50
            truncated += f"\n⚠️ Diff过大，已截断（完整大小: {len(stdout)/1024:.1f}KB）"
            truncated += "\n建议使用外部diff工具查看完整差异"
            truncated += "\n" + "="*50
            return truncated
        
        return stdout

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
        # Git 2.23+推荐使用 git restore --staged
        success, _, stderr = self._run_git_sync(['restore', '--staged', file_path])
        if not success:
            # 回退到旧命令（兼容Git 2.23之前的版本）
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
                # 验证路径安全性
                real_path = os.path.realpath(full_path)
                repo_real_path = os.path.realpath(self._repo_path)
                if not real_path.startswith(repo_real_path + os.sep):
                    return False  # 路径不在仓库内
                
                # 检查文件是否存在且有写权限
                if not os.path.exists(real_path):
                    return False
                if not os.access(real_path, os.W_OK):
                    return False  # 无写权限
                
                os.remove(real_path)
                self.statusChanged.emit()
                return True
            except Exception:
                return False
        else:
            # 恢复已跟踪文件
            # Git 2.23+推荐使用 git restore
            success, _, _ = self._run_git_sync(['restore', file_path])
            if not success:
                # 回退到旧命令（兼容Git 2.23之前的版本）
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
        
        # 详细的错误处理
        error_msg = stderr.strip() if stderr.strip() else stdout.strip()
        if not error_msg:
            error_msg = "提交失败（未知原因）"
        
        # 常见错误的友好提示
        if "nothing to commit" in error_msg.lower() or "no changes added" in error_msg.lower():
            return False, "暂存区为空，请先暂存文件再提交"
        if "please tell me who you are" in error_msg.lower() or "user.name" in error_msg.lower():
            return False, "请先配置Git用户信息（用户名和邮箱）"
        
        logger.error(f"Git commit失败: stdout={stdout}, stderr={stderr}")
        return False, error_msg

    def amend_commit(self, message: str) -> tuple[bool, str]:
        """修改最后一次提交"""
        success, stdout, stderr = self._run_git_sync(['commit', '--amend', '-m', message])
        if success:
            self.statusChanged.emit()
            return True, "修改提交成功"
        return False, stderr or "修改提交失败"

    # ==================== 推送/拉取操作 ====================

    def push(self, remote: str = "origin", branch: str = "", force: bool = False, callback: Callable[[bool, str], None] = None):
        """推送到远程（异步）
        
        Args:
            remote: 远程仓库名
            branch: 分支名
            force: 是否强制推送（危险操作！）
            callback: 完成回调
        """
        self.operationStarted.emit("正在推送...")

        args = ['push']
        if force:
            args.append('--force')  # 强制推送
        args.append(remote)
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
    
    def set_upstream(self, local_branch: str, remote: str, remote_branch: str) -> tuple[bool, str]:
        """设置分支的上游跟踪关系（同步）
        
        Args:
            local_branch: 本地分支名
            remote: 远程仓库名
            remote_branch: 远程分支名
        
        Returns:
            (success, message)
        """
        args = ['branch', '--set-upstream-to', f'{remote}/{remote_branch}', local_branch]
        success, stdout, stderr = self._run_git_sync(args)
        msg = stdout if success else (stderr or "设置上游分支失败")
        return success, msg

    def pull(self, remote: str = "origin", branch: str = "", rebase: bool = False, callback: Callable[[bool, str], None] = None):
        """拉取远程变更（异步）
        
        Args:
            remote: 远程仓库名
            branch: 分支名
            rebase: 是否使用rebase而非merge
            callback: 完成回调
        """
        self.operationStarted.emit("正在拉取...")

        args = ['pull']
        if rebase:
            args.append('--rebase')
        args.append(remote)
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
    
    def fetch_sync(self, remote: str = "origin") -> tuple[bool, str]:
        """获取远程更新（同步）
        
        Args:
            remote: 远程仓库名
        
        Returns:
            (success, message)
        """
        success, stdout, stderr = self._run_git_sync(['fetch', remote], timeout=120)
        msg = stdout if success else (stderr or "获取失败")
        return success, msg

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

    def merge_branch(self, branch: str, callback: Callable[[bool, str], None] = None):
        """合并分支（异步）"""
        self.operationStarted.emit(f"正在合并分支 {branch}...")
        
        def on_finished(success: bool, stdout: str, stderr: str):
            if success:
                self.statusChanged.emit()
            msg = f"已合并分支 {branch}" if success else (stderr or "合并分支失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        self._run_git_async(['merge', branch], on_finished)

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
        """一键操作：暂存 + 提交 + 推送（完全异步）"""
        # 注意：不在这里发送operationStarted，由QuickCommitWorker开始时发送
        # self.operationStarted.emit("正在执行一键提交推送...")
        
        # 异步执行所有步骤
        def do_quick_commit_push():
            """在子线程执行所有Git操作"""
            # 步骤1：暂存所有
            self.progressUpdated.emit(0, "暂存所有变更...")
            if not self.stage_all():
                return False, "暂存失败"
            
            # 步骤2：提交
            self.progressUpdated.emit(33, "提交变更...")
            success, commit_msg = self.commit(message)
            if not success:
                return False, commit_msg
            
            # 步骤3：检查远程仓库
            remotes = self.get_remotes()
            if not remotes:
                return True, "提交成功，但没有配置远程仓库"
            
            # 步骤4：推送（同步执行）
            self.progressUpdated.emit(66, "推送到远程...")
            current_branch = self.get_current_branch()
            args = ['push', '-u', 'origin', current_branch]
            success, stdout, stderr = self._run_git_sync(args, timeout=60)
            
            if success:
                self.progressUpdated.emit(100, "完成")
                return True, "一键提交推送成功"
            else:
                return False, f"推送失败: {stderr or '未知错误'}"
        
        # 异步执行
        def on_finished(success: bool, stdout: str, stderr: str):
            # stdout存储的是(success, msg)元组的第一个值，stderr存储的是第二个值
            # 但这里我们需要特殊处理
            pass
        
        # 使用异步Worker执行
        from PySide6.QtCore import QThread
        
        class QuickCommitWorker(QThread):
            finished = Signal(bool, str)
            
            def __init__(self, parent_service):
                super().__init__()
                self.parent_service = parent_service
            
            def run(self):
                success, msg = do_quick_commit_push()
                self.finished.emit(success, msg)
        
        worker = QuickCommitWorker(self)
        
        def on_worker_finished(success: bool, msg: str):
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        # 在worker开始时发送operationStarted信号
        self.operationStarted.emit("正在执行一键提交推送...")
        
        worker.finished.connect(on_worker_finished)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

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
                # 防止路径遍历攻击：验证路径在仓库内
                real_path = os.path.realpath(full_path)
                repo_real_path = os.path.realpath(self._repo_path)
                if not real_path.startswith(repo_real_path + os.sep):
                    continue  # 跳过不安全的路径
                
                # 限制文件大小，防止读取大文件卡顿
                if os.path.exists(real_path):
                    file_size = os.path.getsize(real_path)
                    if file_size > 1024 * 1024:  # 超过1MB跳过
                        continue
                
                with open(real_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(1024 * 100)  # 最多读100KB
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

    # ==================== Tag标签管理 ====================

    def get_tags(self) -> list[tuple[str, str, str]]:
        """获取Tag列表
        
        Returns:
            list of (tag_name, commit_hash, message)
        """
        success, stdout, _ = self._run_git_sync([
            'tag', '-l', '--format=%(refname:short)|%(objectname:short)|%(contents:subject)'
        ])
        if not success:
            return []
        
        tags = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 2)
            if len(parts) >= 2:
                tag_name = parts[0]
                commit_hash = parts[1]
                message = parts[2] if len(parts) == 3 else ""
                tags.append((tag_name, commit_hash, message))
        
        return tags

    def create_tag(self, name: str, message: str = "", commit: str = "HEAD") -> tuple[bool, str]:
        """创建Tag
        
        Args:
            name: Tag名称
            message: Tag消息（如果提供，创建附注Tag）
            commit: 目标提交（默认HEAD）
        """
        if message:
            # 附注Tag
            args = ['tag', '-a', name, '-m', message, commit]
        else:
            # 轻量级Tag
            args = ['tag', name, commit]
        
        success, _, stderr = self._run_git_sync(args)
        if success:
            return True, f"已创建Tag: {name}"
        return False, stderr or "创建Tag失败"

    def delete_tag(self, name: str) -> tuple[bool, str]:
        """删除本地Tag"""
        success, _, stderr = self._run_git_sync(['tag', '-d', name])
        if success:
            return True, f"已删除Tag: {name}"
        return False, stderr or "删除Tag失败"

    def delete_remote_tag(self, name: str, remote: str = "origin") -> tuple[bool, str]:
        """删除远程Tag"""
        success, _, stderr = self._run_git_sync(['push', remote, '--delete', f'refs/tags/{name}'])
        if success:
            return True, f"已删除远程Tag: {name}"
        return False, stderr or "删除远程Tag失败"

    def push_tag(self, name: str, remote: str = "origin") -> tuple[bool, str]:
        """推送Tag到远程"""
        success, _, stderr = self._run_git_sync(['push', remote, name])
        if success:
            return True, f"已推送Tag: {name}"
        return False, stderr or "推送Tag失败"

    def push_all_tags(self, remote: str = "origin") -> tuple[bool, str]:
        """推送所有Tag到远程"""
        success, _, stderr = self._run_git_sync(['push', remote, '--tags'])
        if success:
            return True, "已推送所有Tag"
        return False, stderr or "推送Tag失败"

    def checkout_tag(self, name: str) -> tuple[bool, str]:
        """切换到Tag（分离头指针状态）"""
        success, _, stderr = self._run_git_sync(['checkout', name])
        if success:
            self.statusChanged.emit()
            return True, f"已切换到Tag: {name}"
        return False, stderr or "切换Tag失败"

    # ==================== 远程仓库管理 ====================

    def add_remote(self, name: str, url: str) -> tuple[bool, str]:
        """添加远程仓库"""
        success, _, stderr = self._run_git_sync(['remote', 'add', name, url])
        if success:
            return True, f"已添加远程仓库: {name}"
        return False, stderr or "添加远程仓库失败"

    def remove_remote(self, name: str) -> tuple[bool, str]:
        """删除远程仓库"""
        success, _, stderr = self._run_git_sync(['remote', 'remove', name])
        if success:
            return True, f"已删除远程仓库: {name}"
        return False, stderr or "删除远程仓库失败"

    def set_remote_url(self, name: str, url: str) -> tuple[bool, str]:
        """修改远程URL"""
        success, _, stderr = self._run_git_sync(['remote', 'set-url', name, url])
        if success:
            return True, f"已修改远程URL: {name}"
        return False, stderr or "修改远程URL失败"

    def get_remote_url(self, name: str) -> str:
        """获取远程URL"""
        success, stdout, _ = self._run_git_sync(['remote', 'get-url', name])
        return stdout.strip() if success else ""

    def get_remote_info(self) -> list[tuple[str, str]]:
        """获取远程仓库详细信息
        
        Returns:
            list of (remote_name, url)
        """
        remotes = self.get_remotes()
        result = []
        for remote in remotes:
            if remote:
                url = self.get_remote_url(remote)
                result.append((remote, url))
        return result

    # ==================== 提交详情 ====================

    def get_commit_files(self, commit_hash: str) -> list[FileChange]:
        """获取提交的变更文件列表"""
        success, stdout, _ = self._run_git_sync([
            'diff-tree', '--no-commit-id', '--name-status', '-r', commit_hash
        ])
        if not success:
            return []
        
        files = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t', 1)
            if len(parts) == 2:
                status_char = parts[0][0]
                file_path = parts[1]
                status = self._parse_status_char(status_char)
                files.append(FileChange(path=file_path, status=status, staged=False))
        
        return files

    def get_commit_diff(self, commit_hash: str) -> str:
        """获取提交的完整diff"""
        success, stdout, _ = self._run_git_sync(['show', commit_hash])
        return stdout if success else ""

    def get_commit_detail(self, commit_hash: str) -> Optional[CommitInfo]:
        """获取提交详细信息"""
        format_str = '%H|%h|%an|%ae|%ad|%s|%b'
        success, stdout, _ = self._run_git_sync([
            'show', '--no-patch', f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M', commit_hash
        ])
        
        if not success or not stdout.strip():
            return None
        
        parts = stdout.strip().split('|', 6)
        if len(parts) >= 6:
            return CommitInfo(
                hash=parts[0],
                short_hash=parts[1],
                author=parts[2],
                email=parts[3],
                date=parts[4],
                message=parts[5] + ('\n' + parts[6] if len(parts) == 7 else '')
            )
        return None

    # ==================== Cherry-pick ====================

    def cherry_pick(self, commit_hash: str) -> tuple[bool, str]:
        """应用指定提交到当前分支"""
        success, stdout, stderr = self._run_git_sync(['cherry-pick', commit_hash])
        if success:
            self.statusChanged.emit()
            return True, f"已应用提交 {commit_hash[:7]}"
        return False, stderr or "Cherry-pick失败"

    def cherry_pick_abort(self) -> tuple[bool, str]:
        """中止cherry-pick操作"""
        success, _, stderr = self._run_git_sync(['cherry-pick', '--abort'])
        if success:
            self.statusChanged.emit()
            return True, "已中止cherry-pick"
        return False, stderr or "中止cherry-pick失败"

    def cherry_pick_continue(self) -> tuple[bool, str]:
        """继续 cherry-pick操作"""
        success, _, stderr = self._run_git_sync(['cherry-pick', '--continue'])
        if success:
            self.statusChanged.emit()
            return True, "已继续cherry-pick"
        return False, stderr or "继续cherry-pick失败"

    # ==================== 克隆仓库 ====================

    def clone(self, url: str, path: str, callback: Callable[[bool, str], None] = None):
        """克隆远程仓库（异步）
        
        Args:
            url: 远程仓库URL
            path: 本地路径
            callback: 完成回调
        """
        self.operationStarted.emit("正在克隆仓库...")
        
        args = ['clone', url, path, '--progress']
        
        def on_finished(success: bool, stdout: str, stderr: str):
            if success:
                msg = f"克隆成功: {path}"
            else:
                msg = stderr or "克隆失败"
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        # 克隆可能很慢，设置较长超时
        self._run_git_async(args, on_finished, timeout=300)
    
    def init(self, path: str) -> tuple[bool, str]:
        """初始化新的Git仓库
        
        Args:
            path: 要初始化的目录路径
        """
        if not path or not os.path.isdir(path):
            return False, "目录不存在"
        
        # 检查是否已经是Git仓库
        git_dir = os.path.join(path, '.git')
        if os.path.isdir(git_dir):
            return False, "该目录已经是 Git 仓库"
        
        # 执行git init
        try:
            result = subprocess.run(
                ['git', 'init'],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                return True, f"已初始化Git仓库: {path}"
            return False, result.stderr or "初始化失败"
        except Exception as e:
            return False, str(e)

    # ==================== Rebase操作 ====================

    def rebase(self, branch: str, callback: Callable[[bool, str], None] = None):
        """变基到指定分支（异步）"""
        self.operationStarted.emit(f"正在变基到 {branch}...")
        
        def on_finished(success: bool, stdout: str, stderr: str):
            if success:
                self.statusChanged.emit()
            msg = f"已变基到 {branch}" if success else (stderr or "Rebase失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        self._run_git_async(['rebase', branch], on_finished)

    def rebase_abort(self) -> tuple[bool, str]:
        """中止rebase操作"""
        success, _, stderr = self._run_git_sync(['rebase', '--abort'])
        if success:
            self.statusChanged.emit()
            return True, "已中止rebase"
        return False, stderr or "中止rebase失败"

    def rebase_continue(self) -> tuple[bool, str]:
        """继续rebase操作"""
        success, _, stderr = self._run_git_sync(['rebase', '--continue'])
        if success:
            self.statusChanged.emit()
            return True, "已继续rebase"
        return False, stderr or "继续rebase失败"

    def rebase_skip(self) -> tuple[bool, str]:
        """跳过当前rebase冲突"""
        success, _, stderr = self._run_git_sync(['rebase', '--skip'])
        if success:
            self.statusChanged.emit()
            return True, "已跳过当前冲突"
        return False, stderr or "跳过失败"

    # ==================== Reflog引用日志 ====================

    def get_reflog(self, count: int = 50) -> list[tuple[str, str, str]]:
        """获取引用日志
        
        Returns:
            list of (hash, ref, message)
        """
        success, stdout, _ = self._run_git_sync(['reflog', f'-{count}', '--format=%H|%gd|%gs'])
        if not success:
            return []
        
        logs = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 2)
            if len(parts) == 3:
                logs.append((parts[0], parts[1], parts[2]))
        
        return logs

    # ==================== Blame代码作者 ====================

    def blame(self, file_path: str) -> list[tuple[int, str, str, str, str]]:
        """获取文件每行的blame信息
        
        Returns:
            list of (line_num, hash, author, date, content)
        """
        success, stdout, _ = self._run_git_sync([
            'blame', '--line-porcelain', file_path
        ])
        if not success:
            return []
        
        # 解析blame输出（简化处理）
        lines = []
        current_hash = ""
        current_author = ""
        current_date = ""
        
        for line in stdout.split('\n'):
            if line and not line.startswith('\t'):
                if line.startswith('author '):
                    current_author = line[7:]
                elif line.startswith('author-time '):
                    import time
                    timestamp = int(line[12:])
                    current_date = time.strftime('%Y-%m-%d %H:%M', time.localtime(timestamp))
                elif len(line.split()) == 4 and line.split()[0].isalnum():
                    current_hash = line.split()[0][:7]
            elif line.startswith('\t'):
                content = line[1:]
                lines.append((len(lines)+1, current_hash, current_author, current_date, content))
        
        return lines

    # ==================== Clean清理 ====================

    def clean_preview(self) -> list[str]:
        """预览将被清理的文件"""
        success, stdout, _ = self._run_git_sync(['clean', '-n', '-d'])
        if not success:
            return []
        
        files = []
        for line in stdout.strip().split('\n'):
            if line.startswith('Would remove '):
                files.append(line[13:])
        return files

    def clean(self, include_directories: bool = True) -> tuple[bool, str]:
        """清理未跟踪文件（危险操作）"""
        args = ['clean', '-f']
        if include_directories:
            args.append('-d')
        
        success, stdout, stderr = self._run_git_sync(args)
        if success:
            self.statusChanged.emit()
            return True, "已清理未跟踪文件"
        return False, stderr or "清理失败"

    # ==================== Config配置 ====================

    def get_config(self, key: str, global_scope: bool = False) -> str:
        """获取Git配置"""
        args = ['config']
        if global_scope:
            args.append('--global')
        args.append(key)
        
        success, stdout, _ = self._run_git_sync(args)
        return stdout.strip() if success else ""

    def set_config(self, key: str, value: str, global_scope: bool = False) -> tuple[bool, str]:
        """设置Git配置"""
        args = ['config']
        if global_scope:
            args.append('--global')
        args.extend([key, value])
        
        success, _, stderr = self._run_git_sync(args)
        if success:
            return True, f"已设置 {key} = {value}"
        return False, stderr or "设置配置失败"

    def get_user_info(self) -> tuple[str, str]:
        """获取用户信息
        
        Returns:
            (name, email)
        """
        name = self.get_config('user.name')
        email = self.get_config('user.email')
        return name, email

    def set_user_info(self, name: str, email: str, global_scope: bool = True) -> tuple[bool, str]:
        """设置用户信息"""
        success1, _ = self.set_config('user.name', name, global_scope)
        success2, _ = self.set_config('user.email', email, global_scope)
        
        if success1 and success2:
            return True, f"已设置用户信息: {name} <{email}>"
        return False, "设置用户信息失败"

    # ==================== 远程分支清理 ====================

    def prune_remote(self, remote: str = "origin") -> tuple[bool, str]:
        """清理已删除的远程分支引用"""
        success, stdout, stderr = self._run_git_sync(['remote', 'prune', remote])
        if success:
            return True, f"已清理远程分支引用: {remote}"
        return False, stderr or "清理失败"

    # ==================== 其他实用命令 ====================

    def diff_with_commit(self, commit_hash: str, file_path: str = "") -> str:
        """对比工作区与指定提交
        
        Args:
            commit_hash: 目标提交
            file_path: 文件路径（可选）
        """
        args = ['diff', commit_hash]
        if file_path:
            args.extend(['--', file_path])
        
        success, stdout, _ = self._run_git_sync(args)
        return stdout if success else ""

    def gc(self, callback: Callable[[bool, str], None] = None):
        """垃圾回收，优化仓库（异步）"""
        self.operationStarted.emit("正在优化仓库...")
        
        def on_finished(success: bool, stdout: str, stderr: str):
            msg = "仓库优化完成" if success else (stderr or "优化失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        self._run_git_async(['gc', '--auto'], on_finished, timeout=60)

    def fsck(self) -> tuple[bool, str]:
        """检查仓库完整性"""
        success, stdout, stderr = self._run_git_sync(['fsck'])
        if success:
            return True, "仓库检查通过"
        return False, stderr or "检查失败"


# 全局单例
gitService = GitService()
