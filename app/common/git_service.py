# coding:utf-8
"""
Git服务层 - 封装所有Git命令操作
提供异步执行和错误处理
"""
import glob
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker
from prismqml import current_task

from .git_graph import (
    CommitGraphRow,
    CommitRef,
    layout_commit_graph,
    parse_commit_refs,
)
from .git_hash_stream import stream_git_hashes
from .git_push_progress import run_git_push_with_progress
from .logger import get_logger
from .prism_task import submit_to_pool

logger = get_logger("GitService")

_HISTORY_SEARCH_TIMEOUT_SECONDS = 300
MAX_HISTORY_RESULTS = 2000
MAX_COMMIT_FILE_PREVIEW = 500
MAX_COMMIT_DIFF_SIZE = 100 * 1024
MAX_BRANCH_RESULTS = 5000
MAX_CLEAN_PREVIEW = 500
MAX_CONFLICT_FILE_SIZE = 100 * 1024
MAX_STATUS_CHANGES = 5000
MAX_TAG_RESULTS = 5000
MAX_FILE_HISTORY_RESULTS = 500
MAX_STASH_RESULTS = 500
MAX_REFLOG_RESULTS = 500
MAX_CONFLICT_RESULTS = 5000
MAX_FILE_CONTENT_SIZE = 100 * 1024
MAX_RULE_FILE_SIZE = 256 * 1024


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
    reverted_by: str = ""
    reverts: str = ""
    parents: list[str] = field(default_factory=list)
    refs: list[CommitRef] = field(default_factory=list)
    graph: Optional[CommitGraphRow] = None


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


@dataclass
class WorktreeInfo:
    """worktree 信息"""
    path: str
    head: str = ""
    branch: str = ""
    detached: bool = False
    bare: bool = False
    prunable: bool = False
    prunable_reason: str = ""
    locked: bool = False
    locked_reason: str = ""


@dataclass
class SubmoduleInfo:
    """submodule 信息"""
    path: str
    hash: str = ""
    status: str = ""
    description: str = ""


@dataclass
class DiffLine:
    """统一 diff 中的一行。"""
    kind: str
    text: str
    old_number: Optional[int] = None
    new_number: Optional[int] = None


@dataclass
class DiffHunk:
    """统一 diff hunk。"""
    header: str
    old_start: int = 0
    old_count: int = 0
    new_start: int = 0
    new_count: int = 0
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class DiffFile:
    """统一 diff 中单个文件的变更摘要。"""
    path: str
    old_path: str = ""
    new_path: str = ""
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    hunks: list[DiffHunk] = field(default_factory=list)
    raw: str = ""


class GitService(QObject):
    """Git服务 - 提供所有Git操作接口"""

    _INDEX_LOCK_RETRY_DELAYS = (0.15, 0.3, 0.6, 1.0, 1.5, 2.0)

    # 信号定义
    statusChanged = Signal()                    # 状态变更
    operationStarted = Signal(str)              # 操作开始
    operationFinished = Signal(bool, str)       # 操作完成(成功/失败, 消息)
    progressUpdated = Signal(int, str)          # 进度更新(百分比, 消息)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._repo_path: Optional[str] = None
        self._mutex = QMutex()
        self._revert_cache_key: tuple[str, str] | None = None
        self._revert_cache: tuple[dict[str, str], dict[str, str]] = ({}, {})
        self._revert_cache_lock = threading.Lock()

    @property
    def repo_path(self) -> Optional[str]:
        return self._repo_path

    @staticmethod
    def _is_git_work_tree_path(path: str) -> bool:
        """校验普通仓库或 linked worktree 路径。"""
        if not path or not os.path.isdir(path):
            return False
        git_marker = os.path.join(path, '.git')
        if not (os.path.isdir(git_marker) or os.path.isfile(git_marker)):
            return False
        try:
            result = subprocess.run(
                ['git', '-C', path, 'rev-parse', '--is-inside-work-tree'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            return result.returncode == 0 and result.stdout.strip().lower() == 'true'
        except FileNotFoundError:
            logger.error("Git未安装或不在PATH中")
            return False
        except Exception as e:
            logger.debug(f"校验 Git 工作树失败 {path}: {e}")
            return False

    def set_repo_path(self, path: str, emit_status: bool = True) -> bool:
        """设置仓库路径"""
        logger.info(f"设置仓库路径: {path}")
        if not self.validate_repo_path(path):
            return False
        return self.activate_repo_path(path, emit_status=emit_status)

    def validate_repo_path(self, path: str) -> bool:
        """验证仓库路径；可安全地在线程池执行，不修改 QObject 状态。"""
        if not path or not os.path.isdir(path):
            logger.warning(f"路径无效: {path}")
            return False

        # 检查目录权限（读取+执行）
        if not os.access(path, os.R_OK | os.X_OK):
            logger.warning(f"目录权限不足: {path}")
            return False

        if not self._is_git_work_tree_path(path):
            logger.warning(f"不是Git仓库: {path}")
            return False

        return True

    def activate_repo_path(self, path: str, emit_status: bool = True) -> bool:
        """激活已经验证的仓库路径；调用方必须位于 Qt 主线程。"""
        self._repo_path = path
        logger.info(f"仓库路径设置成功: {path}")
        if emit_status:
            self.statusChanged.emit()
        return True

    def is_large_repo(self) -> bool:
        """检测是否为大仓库（超过1000个提交）"""
        return self.is_large_repo_at(self._repo_path or "")

    def is_large_repo_at(self, repo_path: str) -> bool:
        """检测指定仓库是否为大仓库，不读取可变的当前仓库路径。"""
        if not repo_path:
            return False

        success, stdout, _ = self._run_git_sync_at(repo_path, ['rev-list', '--count', 'HEAD'])
        if success:
            try:
                count = int(stdout.strip())
                return count > 1000
            except ValueError:
                return False
        return False

    def compute_state_fingerprint(self, repo_path: str) -> str:
        """计算仓库状态指纹,用于轮询检测"外部"(命令行/其他工具)引起的变化。

        覆盖面:工作区/暂存区(status v2)、当前分支与 ahead/behind、所有 refs
        (本地分支/远程分支/tag 的 oid,故 commit 移动/分支增删/tag 增删/fetch 都能感知)、
        stash 列表、以及合并/rebase/cherry-pick/revert 中途态标记文件。

        返回指纹字符串;仓库无效或 status 读取失败时返回空串,
        调用方据此"跳过本轮"而非误触发刷新。
        """
        if not self._is_git_work_tree_path(repo_path):
            return ""

        parts: list[str] = []
        # 工作区/暂存/分支状态(含 unmerged 项 → 冲突文件变化也在内)
        ok, out, _ = self._run_git_sync_at(repo_path, ['status', '--porcelain=v2', '--branch'], timeout=10)
        if not ok:
            return ""  # 读不到状态:跳过本轮,避免拿不确定数据误判
        parts.append(out)
        # 所有 refs 的 oid(空仓库时 show-ref 返回非 0,视为空串,不算失败)
        ok, out, _ = self._run_git_sync_at(repo_path, ['show-ref'], timeout=10)
        parts.append(out if ok else "")
        # stash 列表
        ok, out, _ = self._run_git_sync_at(repo_path, ['stash', 'list'], timeout=10)
        parts.append(out if ok else "")
        # 中途态标记(status v2 未必完整反映"处于合并/变基中途")
        git_dir = os.path.join(repo_path, '.git')
        for marker in ('MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD', 'REVERT_HEAD'):
            parts.append("1" if os.path.exists(os.path.join(git_dir, marker)) else "0")

        import hashlib
        return hashlib.md5("\x00".join(parts).encode('utf-8', 'replace')).hexdigest()

    def _run_git_sync(self, args: list[str], timeout: int = 30) -> tuple[bool, str, str]:
        """同步执行Git命令

        Args:
            args: Git命令参数
            timeout: 超时时间（秒），默认30秒
        """
        return self._run_git_sync_at(self._repo_path or "", args, timeout)

    def _run_git_sync_at(self, repo_path: str, args: list[str], timeout: int = 30) -> tuple[bool, str, str]:
        """在指定仓库快照路径同步执行 Git 命令,用于异步查询防切仓库串读。"""
        if not repo_path:
            return False, "", "未设置仓库路径"

        # -c core.quotepath=false: 让 git 输出原始 UTF-8 文件名,
        # 而非 \\344\\270\\255 八进制转义(否则中文/非ASCII 路径无法被后续命令使用)
        cmd = ['git', '-c', 'core.quotepath=false'] + args
        try:
            for attempt, delay in enumerate((0.0, *self._INDEX_LOCK_RETRY_DELAYS)):
                if delay:
                    logger.debug(
                        "Git 检测到 index.lock，占用可能是瞬态，静默重试第 %d 次",
                        attempt,
                    )
                    time.sleep(delay)
                result = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=timeout,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                )
                if (
                    result.returncode == 0
                    or not self._is_index_lock_error(result.stdout, result.stderr)
                    or attempt == len(self._INDEX_LOCK_RETRY_DELAYS)
                ):
                    return result.returncode == 0, result.stdout, result.stderr
            raise RuntimeError("Git index.lock 重试状态无效")
        except subprocess.TimeoutExpired:
            logger.error(f"Git命令超时: {' '.join(args)}, timeout={timeout}s, repo={repo_path}")
            return False, "", f"操作超时（{timeout}秒）"
        except FileNotFoundError:
            logger.error("Git未安装或不在PATH中")
            return False, "", "Git未安装或不在PATH中"
        except Exception as e:
            logger.exception(f"Git命令异常: {' '.join(args)}, repo={repo_path}, error: {e}")
            return False, "", "Git 操作执行异常，技术详情已记录到日志。"

    @staticmethod
    def _is_index_lock_error(stdout: str, stderr: str) -> bool:
        text = f"{stdout}\n{stderr}".lower()
        return "index.lock" in text and (
            "file exists" in text
            or "already exists" in text
            or "another git process" in text
            or "unable to create" in text
            or "cannot create" in text
        )

    @staticmethod
    def _friendly_git_state_error(lower_detail: str) -> str:
        patterns = (
            (("nothing to commit", "no changes added", "nothing added to commit"), "暂存区为空，请先暂存文件再提交。"),
            (("please tell me who you are", "author identity unknown", "unable to auto-detect email address"), "请先配置 Git 用户信息（用户名和邮箱）。"),
            (("not a git repository", "operation must be run in a work tree"), "当前路径不是有效的 Git 仓库，请先打开或初始化仓库。"),
            (("does not have any commits yet", "bad revision 'head'"), "当前仓库还没有提交，请先完成首次提交。"),
            (("untracked working tree files would be overwritten",), "未跟踪文件会被本次操作覆盖，请先移动、删除或暂存这些文件。"),
            (("contains modified or untracked files", "use --force to delete it"), "工作树中存在未提交修改或未跟踪文件；如确认不再需要，请从“移除”按钮的下拉菜单选择强制删除。"),
            (("would be overwritten by checkout", "would be overwritten by merge", "would be overwritten by switch", "commit your changes or stash them", "cannot rebase: you have unstaged changes", "cannot pull with rebase: you have unstaged changes"), "工作区有未提交的修改，请先提交、暂存或放弃修改后再重试。"),
            (("not fully merged",), "该分支尚未完全合并，删除可能会丢失未合并的提交；如确认不再需要，请选择强制删除。"),
            (("you have unmerged paths", "fix conflicts and then commit", "needs merge", "automatic merge failed", "mergeconflict", "you have not concluded your merge", "merge_head exists"), "当前存在未解决的合并冲突，请先解决冲突后再继续。"),
            (("no cherry-pick or revert in progress", "no rebase in progress", "there is no merge to abort"), "当前没有可继续或中止的 Git 操作。"),
            (("rebase-merge directory", "rebase-apply directory", "rebase in progress"), "当前已有未完成的变基操作，请先继续、跳过或中止该操作。"),
            (("cherry-pick is already in progress", "cherry-pick is currently in progress", "revert is already in progress"), "当前已有未完成的提交应用或撤销操作，请先继续或中止该操作。"),
            (("no stash entries found", "no stash found"), "当前没有可用的 stash 记录。"),
            (("no local changes to save",), "当前没有可保存的工作区修改。"),
            (("empty commit message",), "提交信息不能为空，请填写后重试。"),
            (("detached head", "you are not currently on a branch"), "当前处于分离头指针状态，请先切换或创建分支后再继续。"),
            (("detected dubious ownership",), "Git 因仓库目录所有权异常拒绝操作，请确认该目录可信后再标记为安全目录。"),
        )
        for needles, message in patterns:
            if any(needle in lower_detail for needle in needles):
                return message
        if re.search(r"\bconflicts?\s*(?:\(|:)", lower_detail):
            return "当前存在未解决的合并冲突，请先解决冲突后再继续。"
        return ""

    @staticmethod
    def _friendly_git_remote_error(lower_detail: str) -> str:
        patterns = (
            (("pre-receive hook declined", "protected branch hook declined", "remote rejected"), "远程仓库规则拒绝了本次更新，请检查受保护分支、提交规范或服务器钩子要求。"),
            (("repository not found", "does not appear to be a git repository", "could not read from remote repository"), "远程仓库不存在或当前账号无权访问，请检查远程地址和权限。"),
            (("non-fast-forward", "fetch first", "updates were rejected"), "推送被拒绝：远程有本地没有的提交，请先拉取并合并后再推送。"),
            (("no upstream branch", "has no upstream branch", "no upstream configured"), "当前分支未设置上游，请先设置跟踪分支后再同步。"),
            (("you asked to pull from the remote", "must specify a branch on the command line"), "当前分支没有配置从所选远程拉取哪个分支。请使用“拉取 → 指定拉取”同时选择远程和分支，或先为当前分支设置上游。"),
            (("authentication failed", "permission denied (publickey)", "could not read username", "terminal prompts disabled", "invalid username or password", "requested url returned error: 401", "requested url returned error: 403", "permission to"), "远程认证失败，请检查账号、访问令牌、SSH 密钥及仓库权限。"),
            (("ssl certificate problem", "server certificate verification failed", "schannel: next initializesecuritycontext failed"), "远程服务器证书校验失败，请检查系统时间、证书链或代理设置。"),
            (("could not resolve host", "could not resolve proxy", "failed to connect", "network is unreachable", "connection timed out", "connection refused"), "无法连接远程仓库，请检查网络、代理和远程地址。"),
            (("remote end hung up unexpectedly", "unexpected disconnect", "early eof", "rpc failed"), "与远程仓库的连接中途断开，请检查网络稳定性后重试。"),
            (("need to specify how to reconcile divergent branches", "not possible to fast-forward"), "本地与远程分支已分叉，请选择合并或变基方式后再拉取。"),
        )
        for needles, message in patterns:
            if any(needle in lower_detail for needle in needles):
                return message
        if "remote" in lower_detail and "already exists" in lower_detail:
            return "远程仓库名称已存在，请换一个名称。"
        if "couldn't find remote ref" in lower_detail or "could not find remote ref" in lower_detail:
            return "远程仓库中找不到指定的分支或标签，请刷新远程信息后重新选择。"
        if "no such remote" in lower_detail:
            return "找不到指定的远程仓库，请刷新远程列表或重新配置远程。"
        return ""

    @staticmethod
    def _friendly_git_reference_error(lower_detail: str) -> str:
        if "pathspec" in lower_detail and "did not match" in lower_detail:
            return "找不到指定的分支、标签或文件，请检查名称是否正确。"
        if "src refspec" in lower_detail and "does not match any" in lower_detail:
            return "找不到要推送的本地分支或提交，请先确认当前分支和提交状态。"
        if "remote ref" in lower_detail and "does not exist" in lower_detail:
            return "远程分支或标签不存在，请刷新远程信息后重试。"
        if any(token in lower_detail for token in ("unknown revision", "bad object", "needed a single revision", "ambiguous argument")):
            return "找不到指定的提交或引用，请检查哈希、分支或标签名称。"
        if any(token in lower_detail for token in ("invalid object name", "not a valid object name", "reference is not a tree")):
            return "指定内容不是有效的提交或引用，请重新选择。"
        if "already checked out at" in lower_detail:
            return "该分支已在其他工作树中检出，不能重复检出。"
        if "would clobber existing tag" in lower_detail or re.search(r"\btag\b.*\balready exists\b", lower_detail):
            return "该标签已存在，请换一个标签名称。"
        if re.search(r"\bbranch named .+ already exists\b", lower_detail):
            return "同名分支已存在，请换一个名称或直接使用已有分支。"
        if "cannot delete branch" in lower_detail and ("checked out" in lower_detail or "current branch" in lower_detail):
            return "不能删除当前正在使用的分支，请先切换到其他分支。"
        if "refusing to merge unrelated histories" in lower_detail:
            return "两个仓库历史没有共同起点，不能直接合并；请确认后再选择允许合并无关历史。"
        if "cannot lock ref" in lower_detail or "unable to update local ref" in lower_detail:
            return "分支或标签已被其他 Git 操作更新，请刷新仓库状态后重试。"
        if any(token in lower_detail for token in ("invalid refspec", "not a valid refname", "invalid branch name")):
            return "分支、标签或远程引用名称不合法，请修改名称后重试。"
        return ""

    @staticmethod
    def _friendly_git_storage_error(lower_detail: str) -> str:
        patterns = (
            (("no space left on device", "disk quota exceeded"), "磁盘空间不足，无法完成 Git 操作，请清理空间后重试。"),
            (("read-only file system",), "仓库所在位置为只读，无法写入，请检查磁盘或目录权限。"),
            (("filename too long", "path too long"), "文件路径过长，Git 无法处理，请缩短仓库路径或文件名。"),
            (("permission denied", "access is denied", "operation not permitted"), "Git 无权读写相关文件，请检查仓库目录和文件权限。"),
            (("already exists and is not an empty directory",), "目标目录已存在且不为空，请选择空目录或新的保存位置。"),
            (("unable to create directory", "could not create work tree dir", "cannot create directory"), "无法创建所需目录，请检查路径是否有效以及当前账号是否有写入权限。"),
            (("locked working tree", "worktree is locked", "cannot remove a locked working tree"), "该工作树已锁定，请先确认没有任务使用它，再解除锁定后重试。"),
        )
        for needles, message in patterns:
            if any(needle in lower_detail for needle in needles):
                return message
        return ""

    @staticmethod
    def _friendly_git_feature_error(lower_detail: str) -> str:
        patterns = (
            (("git: 'lfs' is not a git command", "git-lfs: command not found"), "当前系统未安装 Git LFS，请先安装并初始化 Git LFS。"),
            (("no submodule mapping found in .gitmodules", "no url found for submodule path"), "子模块配置不完整，请检查 .gitmodules 中的路径和地址。"),
            (("bad config line", "key does not contain a section", "invalid key"), "Git 配置文件包含无效内容，请检查对应配置项。"),
            (("is a missing but locked working tree", "is already registered worktree"), "工作树记录与磁盘状态不一致，请先清理或修复 worktree 记录。"),
        )
        for needles, message in patterns:
            if any(needle in lower_detail for needle in needles):
                return message
        return ""

    @staticmethod
    def _git_error_for_log(detail: str) -> str:
        """保留诊断信息，同时移除远程 URL 和常见令牌中的凭据。"""
        substitutions = (
            (r"(?i)\b(https?://)[^/\s@]+@", r"\1***@"),
            (r"(?i)([?&](?:access_token|token|password|passwd|auth)=)[^&\s]+", r"\1***"),
            (r"(?i)(authorization:\s*(?:bearer|basic)\s+)\S+", r"\1***"),
            (
                r"\b(?:github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{20,})\b",
                "***",
            ),
        )
        redacted = detail
        for pattern, replacement in substitutions:
            redacted = re.sub(pattern, replacement, redacted)
        return redacted if len(redacted) <= 4000 else redacted[:4000] + "…[已截断]"

    @staticmethod
    def _friendly_git_error(
        error: str, fallback: str, *, branch_name: str = ""
    ) -> str:
        """把需要用户处理的常见 Git 错误转换为可执行的中文提示。"""
        detail = (error or "").strip()
        lower_detail = detail.lower()
        if GitService._is_index_lock_error("", detail):
            return "仓库正被另一个 Git 操作占用，本次操作未执行。请等待其他 Git 操作结束后重试；若确认没有 Git 操作在运行，请关闭相关 Git 工具，删除仓库中的 .git/index.lock 后再重试。"
        if branch_name and re.search(r"\bbranch named .+ already exists\b", detail, re.IGNORECASE):
            return f"分支“{branch_name}”已存在，请换一个名称，或直接使用已有分支。"
        for message in (
            GitService._friendly_git_state_error(lower_detail),
            GitService._friendly_git_remote_error(lower_detail),
            GitService._friendly_git_reference_error(lower_detail),
            GitService._friendly_git_storage_error(lower_detail),
            GitService._friendly_git_feature_error(lower_detail),
        ):
            if message:
                return message
        if detail:
            logger.warning(
                "未识别的 Git 错误，已向用户隐藏技术原文: "
                f"{GitService._git_error_for_log(detail)}"
            )
        fallback = (fallback or "Git 操作失败").strip().rstrip("。.!！")
        return f"{fallback}。请检查仓库状态后重试；技术详情已记录到日志。"

    def _run_git_async(
        self,
        args: list[str],
        callback: Callable[[bool, str, str], None],
        timeout: int = None,
        cwd: Optional[str] = None,
    ):
        """异步执行Git命令
        
        Args:
            args: Git命令参数
            callback: 完成回调
            timeout: 超时时间（秒），默认根据命令类型自动设置
        """
        work_dir = cwd or self._repo_path
        if not work_dir:
            callback(False, "", "未设置仓库路径")
            return

        # 自动设置超时时间
        if timeout is None:
            # 网络操作使用较长超时
            if args[0] in ('push', 'pull', 'fetch', 'clone'):
                timeout = 60  # 60秒
            else:
                timeout = 30  # 本地操作30秒

        return submit_to_pool(
            lambda: self._run_git_sync_at(work_dir, args, timeout),
            on_success=lambda result: callback(*result),
            on_failure=lambda exc: callback(
                False,
                "",
                self._friendly_git_error(str(exc), "Git 后台操作失败"),
            ),
        )

    def _run_git_push_async(
        self,
        args: list[str],
        callback: Callable[[bool, str, str], None],
        timeout: int = 60,
    ) -> None:
        if not self._repo_path:
            callback(False, "", "未设置仓库路径")
            return
        command = ['git', '-c', 'core.quotepath=false'] + args
        repo_path = self._repo_path

        def work() -> tuple[bool, str, str]:
            task = current_task()
            result = run_git_push_with_progress(
                command,
                repo_path,
                timeout,
                lambda percent, message: task.report_progress(
                    (percent, message)
                ),
            )
            return result.success, result.stdout, result.stderr

        def report_progress(update: object) -> None:
            percent, message = update
            self.progressUpdated.emit(int(percent), str(message))

        return submit_to_pool(
            work,
            on_success=lambda result: callback(*result),
            on_failure=lambda exc: callback(
                False,
                "",
                self._friendly_git_error(str(exc), "Git 推送任务失败"),
            ),
            on_progress=report_progress,
        )

    def _run_git_push_sync(
        self,
        args: list[str],
        timeout: int,
        on_progress: Callable[[int, str], None] = None,
    ) -> tuple[bool, str, str]:
        if not self._repo_path:
            return False, "", "未设置仓库路径"
        command = ['git', '-c', 'core.quotepath=false'] + args
        result = run_git_push_with_progress(
            command,
            self._repo_path,
            timeout,
            on_progress or self.progressUpdated.emit,
        )
        return result.success, result.stdout, result.stderr

    # ==================== 状态查询 ====================

    def get_status(self) -> list[FileChange]:
        """获取工作区状态"""
        success, stdout, stderr = self._run_git_sync(
            ['status', '--porcelain=v1', '-z', '-uall']
        )
        if not success:
            return []
        return self._parse_status_output(stdout)

    def get_status_at(self, repo_path: str) -> list[FileChange]:
        """获取指定仓库路径的工作区状态,不读取当前 self._repo_path。"""
        success, stdout, stderr = self._run_git_sync_at(
            repo_path, ['status', '--porcelain=v1', '-z', '-uall']
        )
        if not success:
            return []
        return self._parse_status_output(stdout)[:MAX_STATUS_CHANGES]

    def _parse_status_output(self, stdout: str) -> list[FileChange]:
        """解析 git status --porcelain=v1 输出。"""
        if '\0' in stdout:
            return self._parse_nul_status_output(stdout)
        changes = []
        # 注意:不能用 stdout.strip(),会删掉首行前导空格导致 porcelain 列偏移
        # (" M file.txt" 的行首空格表示 index 状态为空,有意义)
        for line in stdout.split('\n'):
            if len(line) < 3:
                continue

            # 解析状态: XY PATH (X=暂存区, Y=工作区, 第3字符起为路径)
            index_status = line[0]   # 暂存区状态
            work_status = line[1]    # 工作区状态
            path = line[3:].rstrip('\r\n')
            # 处理重命名情况
            if ' -> ' in path:
                path = path.split(' -> ')[1]
            # 兼容未使用 -z 的旧调用输出。
            if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
                path = path[1:-1]

            # 确定文件状态
            if index_status == '?' and work_status == '?':
                changes.append(FileChange(path, FileStatus.UNTRACKED, False))
            else:
                # 暂存区有变更
                if index_status != ' ' and index_status != '?':
                    status = self._parse_status_char(index_status)
                    changes.append(FileChange(path, status, True))

                # 工作区有变更（未暂存）
                # 注意：同一文件可能同时有暂存和未暂存的修改，两个都要显示
                if work_status != ' ' and work_status != '?':
                    status = self._parse_status_char(work_status)
                    changes.append(FileChange(path, status, False))

        return changes

    def _parse_nul_status_output(self, stdout: str) -> list[FileChange]:
        """解析 -z 输出；路径原样返回，重命名记录额外消费旧路径字段。"""
        changes = []
        records = stdout.split('\0')
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if len(record) < 3:
                continue
            index_status = record[0]
            work_status = record[1]
            path = record[3:]
            if index_status in {'R', 'C'} or work_status in {'R', 'C'}:
                # porcelain v1 -z 使用 "XY new-path\0old-path\0"，界面统一展示新路径。
                if index < len(records):
                    index += 1
            if index_status == '?' and work_status == '?':
                changes.append(FileChange(path, FileStatus.UNTRACKED, False))
                continue
            if index_status not in {' ', '?'}:
                changes.append(FileChange(
                    path, self._parse_status_char(index_status), True
                ))
            if work_status not in {' ', '?'}:
                changes.append(FileChange(
                    path, self._parse_status_char(work_status), False
                ))
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

    def get_current_branch_at(self, repo_path: str) -> str:
        """获取指定仓库路径的当前分支名,不读取当前 self._repo_path。"""
        success, stdout, _ = self._run_git_sync_at(repo_path, ['rev-parse', '--abbrev-ref', 'HEAD'])
        return stdout.strip() if success else ""

    def get_head_at(self, repo_path: str) -> str:
        """读取指定仓库的 HEAD；空仓库或无效仓库返回空串。"""
        success, stdout, _ = self._run_git_sync_at(
            repo_path, ['rev-parse', '--verify', 'HEAD']
        )
        return stdout.strip() if success else ""

    def get_raw_diff_at(
        self, repo_path: str, staged: bool = False
    ) -> tuple[bool, str, str]:
        """读取未截断的原始差异，供需要完整快照的后端能力使用。

        UI 展示仍使用 ``get_diff`` 的大小保护；此接口不做截断，调用方必须
        自行应用可配置的输入限制，并且不得在主线程调用。
        """
        args = ['diff', '--no-ext-diff', '--full-index', '--find-renames']
        if staged:
            args.append('--cached')
        return self._run_git_sync_at(repo_path, args)

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
                # 去掉前导的 '* '(当前分支) / '+ '(worktree 检出的分支) / '  '
                # 使用lstrip避免Windows编码问题导致的空格丢失
                line = line.lstrip('*+ ').strip()

                # 处理分离头指针状态: (HEAD detached at xxx)
                if line.startswith('(HEAD'):
                    # 提取commit hash并显示中文
                    import re
                    match = re.search(r'at\s+([a-f0-9]+)', line)
                    if match:
                        commit_hash = match.group(1)[:7]
                        name = f"分离头指针 (Detached HEAD) @ {commit_hash}"
                    else:
                        name = "分离头指针 (Detached HEAD)"
                    tracking = ""
                    ahead = behind = 0
                    branches.append(BranchInfo(
                        name=name,
                        is_current=is_current,
                        is_remote=False,
                        tracking=tracking,
                        ahead=ahead,
                        behind=behind
                    ))
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0]
                    tracking = ""
                    ahead = behind = 0

                    # 解析追踪信息 - 使用正则匹配commit hash后的[tracking]格式
                    # 格式: branch_name hash [tracking:status] message
                    # 需要跳过分支名中可能包含的方括号（如[fe]xxx）
                    import re
                    # 匹配 commit hash (7-40位十六进制) 后面的 [xxx] 追踪信息
                    tracking_match = re.search(r'\s[a-f0-9]{7,40}\s+\[([^\]]+)\]', line)
                    if tracking_match:
                        tracking_info = tracking_match.group(1)
                        if ':' in tracking_info:
                            tracking = tracking_info.split(':')[0]
                        else:
                            tracking = tracking_info
                        # 解析领先/落后数(格式如 "origin/main: ahead 2, behind 1")
                        ahead_m = re.search(r'ahead\s+(\d+)', tracking_info)
                        behind_m = re.search(r'behind\s+(\d+)', tracking_info)
                        ahead = int(ahead_m.group(1)) if ahead_m else 0
                        behind = int(behind_m.group(1)) if behind_m else 0

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

        return branches[:MAX_BRANCH_RESULTS]

    _REVERT_TARGET_PATTERN = re.compile(
        r"^This reverts commit ([0-9a-f]{40}|[0-9a-f]{64})\.$",
        re.IGNORECASE | re.MULTILINE,
    )

    @classmethod
    def _parse_revert_relations(cls, stdout: str) -> tuple[dict[str, str], dict[str, str]]:
        """解析 Git 标准正文，返回被撤销与撤销目标两张映射。"""
        reverted_by: dict[str, str] = {}
        reverts: dict[str, str] = {}
        for raw_record in stdout.split("\x00"):
            record = raw_record.strip("\r\n")
            if not record:
                continue
            reverting_hash, separator, message = record.partition("\n")
            if not separator:
                continue
            match = cls._REVERT_TARGET_PATTERN.search(message)
            if match:
                target_hash = match.group(1).lower()
                reverting_hash = reverting_hash.lower()
                reverted_by.setdefault(target_hash, reverting_hash)
                reverts[reverting_hash] = target_hash
        return reverted_by, reverts

    def _get_revert_relations_at(
        self, repo_path: str
    ) -> tuple[dict[str, str], dict[str, str]]:
        """获取当前 HEAD 可达历史的撤销关系，并按仓库与 HEAD 缓存。"""
        success, stdout, _ = self._run_git_sync_at(repo_path, ['rev-parse', '--verify', 'HEAD'])
        if not success:
            return {}, {}
        cache_key = (os.path.normcase(os.path.realpath(repo_path)), stdout.strip())
        with self._revert_cache_lock:
            if cache_key == self._revert_cache_key:
                return self._revert_cache

        success, stdout, stderr = self._run_git_sync_at(repo_path, [
            'log', '--format=%H%n%B%x00', '--grep=This reverts commit ',
            '--fixed-strings', '--regexp-ignore-case', cache_key[1],
        ])
        if not success:
            logger.warning(f"读取撤销关系失败: {stderr or '未知错误'}")
            return {}, {}
        relations = self._parse_revert_relations(stdout)
        with self._revert_cache_lock:
            self._revert_cache_key = cache_key
            self._revert_cache = relations
        return relations

    def _mark_reverted_commits_at(
        self, repo_path: str, commits: list[CommitInfo]
    ) -> list[CommitInfo]:
        reverted_by, reverts = self._get_revert_relations_at(repo_path)
        for commit in commits:
            commit_hash = commit.hash.lower()
            commit.reverted_by = reverted_by.get(commit_hash, "")
            commit.reverts = reverts.get(commit_hash, "")
        return commits

    def get_log(self, count: int = 50, skip: int = 0, fast_mode: bool = False) -> list[CommitInfo]:
        """获取提交历史
        
        Args:
            count: 获取数量
            skip: 跳过前N条记录（用于分页）
            fast_mode: 快速模式（大仓库优化）
        """
        return self.get_log_at(self._repo_path or "", count, skip, fast_mode)

    def get_log_at(
        self, repo_path: str, count: int = 50, skip: int = 0, fast_mode: bool = False
    ) -> list[CommitInfo]:
        """获取指定仓库快照的提交历史。"""
        safe_skip = max(0, skip)
        safe_count = min(
            max(0, count), max(0, MAX_HISTORY_RESULTS - safe_skip)
        )
        if safe_count == 0:
            return []
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log',
            f'-{safe_count}',
            f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M'
        ]
        
        # 大仓库优化：仅显示重要提交
        if fast_mode:
            cmd.append('--first-parent')  # 仅显示第一父提交，加速查询
        
        if safe_skip > 0:
            cmd.append(f'--skip={safe_skip}')

        success, stdout, _ = self._run_git_sync_at(repo_path, cmd)

        if not success:
            return []

        commits = self._parse_commit_log(stdout, repo_path)
        return self._mark_reverted_commits_at(repo_path, commits)

    _GRAPH_LOG_FORMAT = (
        "%H%x00%P%x00%h%x00%an%x00%ae%x00%ad%x00%s%x00%D%x00"
    )

    @staticmethod
    def _graph_commit_from_fields(fields: list[str]) -> Optional[CommitInfo]:
        if len(fields) != 8:
            logger.warning(f"提交图记录字段数异常: {len(fields)}")
            return None
        full_hash, parents, short_hash, author, email, date, message, decorations = fields
        refs = list(parse_commit_refs(decorations))
        branches = [ref.name for ref in refs if ref.kind == "branch"]
        return CommitInfo(
            hash=full_hash,
            short_hash=short_hash,
            author=author,
            email=email,
            date=date,
            message=message,
            branch=" · ".join(branches),
            parents=parents.split() if parents else [],
            refs=refs,
        )

    @classmethod
    def _parse_graph_commit_log(cls, stdout: str) -> list[CommitInfo]:
        commits: list[CommitInfo] = []
        fields = stdout.split("\x00")
        if fields and not fields[-1].strip("\r\n"):
            fields.pop()
        for start in range(0, len(fields), 8):
            record_fields = fields[start:start + 8]
            if record_fields:
                record_fields[0] = record_fields[0].lstrip("\r\n")
            commit = cls._graph_commit_from_fields(record_fields)
            if commit is not None:
                commits.append(commit)
        return commits

    def get_graph_log_at(
        self,
        repo_path: str,
        count: int = 50,
        skip: int = 0,
        include_all_refs: bool = False,
    ) -> list[CommitInfo]:
        """获取当前 HEAD 或全部引用的提交图分页。"""
        safe_skip = max(0, skip)
        safe_count = min(max(0, count), MAX_HISTORY_RESULTS)
        if safe_skip >= MAX_HISTORY_RESULTS:
            return []
        safe_end = min(safe_skip + safe_count, MAX_HISTORY_RESULTS)
        if safe_count == 0 or safe_skip >= safe_end:
            return []
        cmd = [
            "log",
            "--topo-order",
            "--decorate=full",
            f"--max-count={safe_end}",
            f"--format={self._GRAPH_LOG_FORMAT}",
            "--date=format:%Y-%m-%d %H:%M",
        ]
        if include_all_refs:
            cmd.insert(1, "--all")
        success, stdout, stderr = self._run_git_sync_at(repo_path, cmd)
        if not success:
            logger.warning(f"获取提交图失败: {stderr or '未知错误'}")
            return []
        commits = self._parse_graph_commit_log(stdout)
        rows = layout_commit_graph(
            (commit.hash, commit.parents) for commit in commits
        )
        for commit, row in zip(commits, rows):
            commit.graph = row
        self._mark_reverted_commits_at(repo_path, commits)
        return commits[safe_skip:safe_end]

    def _parse_commit_log(self, stdout: str, repo_path: str) -> list[CommitInfo]:
        """解析统一的提交日志格式。"""
        commits = []
        current_branch = self.get_current_branch_at(repo_path)

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

    def _resolve_commit_hash(
        self, repo_path: str, query: str, include_all_refs: bool = False
    ) -> str:
        """解析选定历史范围内唯一的提交对象前缀。"""
        if not re.fullmatch(r"[0-9a-fA-F]{4,64}", query):
            return ""

        success, stdout, _ = self._run_git_sync_at(repo_path, [
            'rev-parse', f'--disambiguate={query.lower()}'
        ])
        candidates = stdout.splitlines() if success else []
        if len(candidates) != 1:
            return ""

        commit_hash = candidates[0]
        success, object_type, _ = self._run_git_sync_at(
            repo_path, ['cat-file', '-t', commit_hash]
        )
        if not success or object_type.strip() != 'commit':
            return ""

        if include_all_refs:
            in_head, _, _ = self._run_git_sync_at(repo_path, [
                'merge-base', '--is-ancestor', commit_hash, 'HEAD'
            ])
            if in_head:
                return commit_hash
            reachable, refs, _ = self._run_git_sync_at(repo_path, [
                'for-each-ref', '--format=%(refname)',
                f'--contains={commit_hash}',
                'refs/heads', 'refs/remotes', 'refs/tags',
            ])
            return commit_hash if reachable and refs.strip() else ""

        reachable, _, _ = self._run_git_sync_at(repo_path, [
            'merge-base', '--is-ancestor', commit_hash, 'HEAD'
        ])
        return commit_hash if reachable else ""

    def _search_text_commit_hashes(
        self,
        repo_path: str,
        query: str,
        count: int,
        include_all_refs: bool = False,
    ) -> list[str]:
        """分别按消息和作者搜索候选提交，并去重。"""
        hashes = []
        for filter_arg in (f'--grep={query}', f'--author={query}'):
            cmd = ['log']
            if include_all_refs:
                cmd.append('--all')
            cmd.extend([
                f'-{count}', '--format=%H', filter_arg,
                '--regexp-ignore-case', '--fixed-strings',
            ])
            success, stdout, _ = self._run_git_sync_at(repo_path, cmd)
            if success:
                hashes.extend(line for line in stdout.splitlines() if line)

        return list(dict.fromkeys(hashes))

    def _search_path_commit_hashes(
        self,
        repo_path: str,
        query: str,
        count: int,
        include_all_refs: bool = False,
    ) -> list[str]:
        """逐父搜索文件路径命中的提交。"""
        cmd_prefix = ['log', '-m']
        if include_all_refs:
            cmd_prefix.append('--all')
        cmd_prefix.extend([f'-{count}', '--format=%H'])

        path_query = glob.escape(query.replace('\\', '/'))
        success, stdout, _ = self._run_git_sync_at(repo_path, [
            *cmd_prefix, '--', f':(icase,glob)**/*{path_query}*'
        ])
        if not success:
            return []
        return list(dict.fromkeys(line for line in stdout.splitlines() if line))

    @staticmethod
    def _diff_search_command(
        query: str, count: int, include_all_refs: bool
    ) -> list[str]:
        cmd = ['log', '-m']
        if include_all_refs:
            cmd.append('--all')
        cmd.extend([
            f'-{count}', '--format=%H', f'-G{re.escape(query)}',
            '--regexp-ignore-case',
        ])
        return cmd

    def _search_diff_commit_hashes(
        self,
        repo_path: str,
        query: str,
        count: int,
        include_all_refs: bool = False,
    ) -> list[str]:
        """逐父搜索补丁中新增、删除行命中的提交。"""
        cmd = self._diff_search_command(query, count, include_all_refs)
        success, stdout, _ = self._run_git_sync_at(repo_path, cmd)
        if not success:
            return []
        return list(dict.fromkeys(line for line in stdout.splitlines() if line))

    def _stream_diff_commit_hashes(
        self,
        repo_path: str,
        query: str,
        count: int,
        include_all_refs: bool,
        on_progress: Callable[[list[str]], None],
    ) -> list[str]:
        """流式搜索补丁内容，并在任务取消时终止旧 Git 进程。"""
        try:
            task = current_task()
        except RuntimeError:
            task = None
        args = self._diff_search_command(query, count, include_all_refs)
        result = stream_git_hashes(
            ['git', '-c', 'core.quotepath=false', *args],
            repo_path,
            timeout=_HISTORY_SEARCH_TIMEOUT_SECONDS,
            creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            ),
            cancel_requested=lambda: bool(task and task.cancel_requested),
            on_progress=on_progress,
        )
        if result.cancelled and task is not None:
            task.raise_if_cancelled()
        if not result.success:
            logger.warning("Git 补丁内容搜索未完整结束: %s", result.error)
        return result.hashes

    def _search_changed_commit_hashes(
        self,
        repo_path: str,
        query: str,
        count: int,
        include_all_refs: bool = False,
    ) -> list[str]:
        """搜索文件路径以及补丁中新增、删除行命中的提交。"""
        hashes = [
            *self._search_path_commit_hashes(
                repo_path, query, count, include_all_refs
            ),
            *self._search_diff_commit_hashes(
                repo_path, query, count, include_all_refs
            ),
        ]
        return list(dict.fromkeys(hashes))

    def _load_search_commits_at(
        self, repo_path: str, hashes: list[str], count: int
    ) -> list[CommitInfo]:
        unique_hashes = list(dict.fromkeys(
            hash_value for hash_value in hashes if hash_value
        ))
        if not unique_hashes:
            return []
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log', f'-{count}', f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M', '--no-walk=sorted',
            *unique_hashes,
        ]
        success, stdout, _ = self._run_git_sync_at(repo_path, cmd)
        if not success:
            return []
        commits = self._parse_commit_log(stdout, repo_path)
        return self._mark_reverted_commits_at(repo_path, commits)

    def _search_fast_commit_hashes(
        self,
        repo_path: str,
        query: str,
        count: int,
        include_all_refs: bool,
    ) -> list[str]:
        """搜索无需扫描补丁内容的消息、作者和路径候选。"""
        return [
            *self._search_text_commit_hashes(
                repo_path, query, count, include_all_refs
            ),
            *self._search_path_commit_hashes(
                repo_path, query, count, include_all_refs
            ),
        ]

    def _progressive_search_hashes_at(
        self,
        repo_path: str,
        query: str,
        count: int,
        include_all_refs: bool,
        progress_callback: Callable[[list[CommitInfo]], None],
    ) -> list[str]:
        base_hashes = self._search_fast_commit_hashes(
            repo_path, query, count, include_all_refs
        )
        last_preview: tuple[str, ...] | None = None

        def publish_diff(diff_hashes: list[str]) -> None:
            nonlocal last_preview
            commits = self._load_search_commits_at(
                repo_path, [*base_hashes, *diff_hashes], count
            )
            signature = tuple(commit.hash for commit in commits)
            if signature != last_preview:
                last_preview = signature
                progress_callback(commits)

        publish_diff([])
        diff_hashes = self._stream_diff_commit_hashes(
            repo_path, query, count, include_all_refs, publish_diff
        )
        return [*base_hashes, *diff_hashes]

    def _build_commit_search_command(
        self,
        repo_path: str,
        query: str,
        search_type: str,
        count: int,
        include_all_refs: bool = False,
    ) -> list[str]:
        """构造提交搜索命令；空列表表示没有候选结果。"""
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log', f'-{count}', f'--format={format_str}',
            '--date=format:%Y-%m-%d %H:%M'
        ]
        text_filters = {
            'message': f'--grep={query}',
            'author': f'--author={query}',
        }
        if search_type in text_filters:
            if include_all_refs:
                cmd.insert(1, '--all')
            cmd.extend([text_filters[search_type], '--regexp-ignore-case', '--fixed-strings'])
            return cmd

        resolved_hash = self._resolve_commit_hash(
            repo_path, query, include_all_refs
        )
        hashes = (
            [resolved_hash]
            if resolved_hash
            else [
                *self._search_text_commit_hashes(
                    repo_path, query, count, include_all_refs
                ),
                *self._search_changed_commit_hashes(
                    repo_path, query, count, include_all_refs
                ),
            ]
        )
        if not hashes:
            return []
        cmd.extend(['--no-walk=sorted', *hashes])
        return cmd

    def search_commits(
        self,
        query: str,
        search_type: str = "all",
        count: int = 50,
        include_all_refs: bool = False,
    ) -> list[CommitInfo]:
        """搜索提交记录
        
        Args:
            query: 搜索关键词
            search_type: 搜索类型（"all"=消息/作者/哈希/文件/增删内容,
                "message"=提交信息, "author"=作者）
            count: 最大返回数量
        """
        repo_path = self._repo_path or ""
        return self.search_commits_at(
            repo_path, query, search_type, count, include_all_refs
        )

    def search_commits_at(
        self,
        repo_path: str,
        query: str,
        search_type: str = "all",
        count: int = 50,
        include_all_refs: bool = False,
    ) -> list[CommitInfo]:
        """搜索指定仓库快照，避免异步切仓库导致多步命令串读。"""
        query = query.strip()
        if not query:
            return self.get_log_at(repo_path, count=count)

        cmd = self._build_commit_search_command(
            repo_path, query, search_type, count, include_all_refs
        )
        if not cmd:
            return []
        success, stdout, _ = self._run_git_sync_at(repo_path, cmd)
        if not success:
            return []

        commits = self._parse_commit_log(stdout, repo_path)
        return self._mark_reverted_commits_at(repo_path, commits)

    def search_commits_progressively_at(
        self,
        repo_path: str,
        query: str,
        search_type: str,
        count: int,
        include_all_refs: bool,
        progress_callback: Callable[[list[CommitInfo]], None],
    ) -> list[CommitInfo]:
        """先发布快速候选，再流式补齐增删内容命中的提交。"""
        query = query.strip()
        if not query or search_type != "all":
            return self.search_commits_at(
                repo_path, query, search_type, count, include_all_refs
            )

        resolved_hash = self._resolve_commit_hash(
            repo_path, query, include_all_refs
        )
        if resolved_hash:
            return self._load_search_commits_at(
                repo_path, [resolved_hash], count
            )

        hashes = self._progressive_search_hashes_at(
            repo_path,
            query,
            count,
            include_all_refs,
            progress_callback,
        )
        return self._load_search_commits_at(repo_path, hashes, count)

    def _path_in_repo(self, file_path: str) -> bool:
        """校验文件路径在仓库内(防 ../ 遍历或绝对路径越界)。"""
        if not file_path or file_path.startswith('-'):
            return False
        try:
            repo_real = os.path.realpath(self._repo_path)
            target_real = os.path.realpath(os.path.join(self._repo_path, file_path))
            return target_real == repo_real or target_real.startswith(repo_real + os.sep)
        except Exception:
            return False

    @staticmethod
    def _strip_diff_path(value: str) -> str:
        """把 diff 头里的 a/path、b/path、/dev/null 规整成仓库相对路径。"""
        path = (value or "").strip()
        if path == "/dev/null":
            return ""
        if path.startswith('"') and path.endswith('"') and len(path) >= 2:
            path = path[1:-1]
        if path.startswith("a/") or path.startswith("b/"):
            path = path[2:]
        return path

    @staticmethod
    def _diff_file_from_header(line: str) -> DiffFile:
        payload = line[len("diff --git "):]
        parts = payload.split(" b/", 1)
        if len(parts) == 2:
            old_path = GitService._strip_diff_path(parts[0])
            new_path = GitService._strip_diff_path("b/" + parts[1])
        else:
            old_path = ""
            new_path = ""
        return DiffFile(path=new_path or old_path, old_path=old_path, new_path=new_path)

    @staticmethod
    def _parse_hunk_header(line: str) -> DiffHunk:
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not match:
            return DiffHunk(header=line)
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        return DiffHunk(line, old_start, old_count, new_start, new_count)

    @staticmethod
    def _finish_diff_file(files: list[DiffFile], current: Optional[DiffFile], raw_lines: list[str]) -> None:
        if not current:
            return
        current.raw = "\n".join(raw_lines)
        if current.raw and not current.raw.endswith("\n"):
            current.raw += "\n"
        if current.status == "modified":
            if current.old_path == "" and current.new_path:
                current.status = "added"
            elif current.new_path == "" and current.old_path:
                current.status = "deleted"
        files.append(current)

    @staticmethod
    def parse_unified_diff(raw_diff: str) -> list[DiffFile]:
        """解析 unified diff,供摘要、文件过滤和测试验证复用。"""
        files: list[DiffFile] = []
        current: Optional[DiffFile] = None
        hunk: Optional[DiffHunk] = None
        raw_lines: list[str] = []
        old_no = new_no = 0

        for line in (raw_diff or "").splitlines():
            if line.startswith("diff --git "):
                GitService._finish_diff_file(files, current, raw_lines)
                current = GitService._diff_file_from_header(line)
                hunk = None
                raw_lines = [line]
                continue
            if current is None:
                current = DiffFile(path="")
            raw_lines.append(line)
            if line.startswith("new file mode"):
                current.status = "added"
            elif line.startswith("deleted file mode"):
                current.status = "deleted"
            elif line.startswith("rename from "):
                current.status = "renamed"
                current.old_path = line[len("rename from "):]
            elif line.startswith("rename to "):
                current.status = "renamed"
                current.new_path = line[len("rename to "):]
                current.path = current.new_path
            elif line.startswith("--- "):
                current.old_path = GitService._strip_diff_path(line[4:])
            elif line.startswith("+++ "):
                current.new_path = GitService._strip_diff_path(line[4:])
                current.path = current.new_path or current.old_path
            elif line.startswith("@@"):
                hunk = GitService._parse_hunk_header(line)
                current.hunks.append(hunk)
                old_no = hunk.old_start
                new_no = hunk.new_start
            elif hunk is not None:
                old_no, new_no = GitService._append_diff_line(current, hunk, line, old_no, new_no)

        GitService._finish_diff_file(files, current, raw_lines)
        return [f for f in files if f.raw or f.path or f.hunks]

    @staticmethod
    def _append_diff_line(file_diff: DiffFile, hunk: DiffHunk, line: str, old_no: int, new_no: int) -> tuple[int, int]:
        prefix = line[:1]
        text = line[1:] if prefix in (" ", "+", "-", "\\") else line
        if prefix == "+":
            hunk.lines.append(DiffLine("added", text, None, new_no))
            file_diff.additions += 1
            return old_no, new_no + 1
        if prefix == "-":
            hunk.lines.append(DiffLine("deleted", text, old_no, None))
            file_diff.deletions += 1
            return old_no + 1, new_no
        if prefix == " ":
            hunk.lines.append(DiffLine("context", text, old_no, new_no))
            return old_no + 1, new_no + 1
        hunk.lines.append(DiffLine("meta", text, None, None))
        return old_no, new_no

    @staticmethod
    def filter_unified_diff(raw_diff: str, file_path: str) -> str:
        """从多文件 diff 中取出指定文件的完整 diff 段。"""
        target = (file_path or "").strip()
        if not target:
            return raw_diff or ""
        matches = []
        for file_diff in GitService.parse_unified_diff(raw_diff):
            paths = {file_diff.path, file_diff.old_path, file_diff.new_path}
            if target in paths:
                matches.append(file_diff.raw)
        return "\n".join(matches).strip("\n")

    def get_diff(self, file_path: str, staged: bool = False) -> str:
        """获取文件差异"""
        if not self._path_in_repo(file_path):
            return ""
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
        success, _ = self._stage_all_result()
        return success

    def _stage_all_result(self) -> tuple[bool, str]:
        """暂存所有变更，并保留可供组合操作展示的失败原因。"""
        success, stdout, stderr = self._run_git_sync(['add', '-A'])
        if success:
            self.statusChanged.emit()
            return True, "暂存成功"
        return False, self._friendly_git_error(stderr or stdout, "暂存失败")

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
        return self.commit_at(self._repo_path or "", message)

    def commit_at(self, repo_path: str, message: str) -> tuple[bool, str]:
        """在指定仓库提交，避免异步流程切换仓库后写错目标。"""
        if not message.strip():
            return False, "提交信息不能为空"

        success, stdout, stderr = self._run_git_sync_at(
            repo_path, ['commit', '-m', message]
        )
        if success:
            self.statusChanged.emit()
            return True, "提交成功"
        
        # 详细的错误处理
        error_msg = self._friendly_git_error(
            stderr if stderr.strip() else stdout,
            "提交失败（未知原因）",
        )
        
        # 常见错误的友好提示
        if "nothing to commit" in error_msg.lower() or "no changes added" in error_msg.lower():
            return False, "暂存区为空，请先暂存文件再提交"
        if "please tell me who you are" in error_msg.lower() or "user.name" in error_msg.lower():
            return False, "请先配置Git用户信息（用户名和邮箱）"
        
        logger.error(f"Git commit失败: stdout={stdout}, stderr={stderr}")
        return False, error_msg

    def amend_commit(self, message: str) -> tuple[bool, str]:
        """修改最后一次提交"""
        # 空仓库无提交可改
        has_head, _, _ = self._run_git_sync(['rev-parse', '--verify', 'HEAD'])
        if not has_head:
            return False, "当前没有可修改的提交(空仓库)"
        success, stdout, stderr = self._run_git_sync(['commit', '--amend', '-m', message])
        if success:
            self.statusChanged.emit()
            return True, "修改提交成功"
        return False, self._friendly_git_error(stderr, "修改提交失败")

    def is_head_pushed(self) -> bool:
        """最近一次提交(HEAD)是否已推送到上游。

        用于 amend 前的安全判断:已推送的提交被 amend 后本地与远端历史分叉,
        需强制推送才能同步,应向用户告警。判定规则:
          - 无 HEAD(空仓库)     → False(无提交可谈"已推送")
          - 无上游分支           → False(本地分支从未推送)
          - HEAD 是上游的祖先    → True(HEAD 已包含在远端,即已推送)
          - 否则                 → False(HEAD 领先上游,最近提交未推送)
        """
        has_head, _, _ = self._run_git_sync(['rev-parse', '--verify', 'HEAD'])
        if not has_head:
            return False
        # 解析上游引用(@{u});无上游时该命令失败
        has_upstream, _, _ = self._run_git_sync(
            ['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'])
        if not has_upstream:
            return False
        # HEAD 是上游祖先 → 已被远端包含 → 已推送
        is_ancestor, _, _ = self._run_git_sync(
            ['merge-base', '--is-ancestor', 'HEAD', '@{u}'])
        return is_ancestor

    # ==================== 推送/拉取操作 ====================

    def _current_branch_without_upstream(self) -> str:
        """返回没有上游跟踪的当前分支；分离头指针或已有上游时返回空串。"""
        branch = self.get_current_branch()
        if not branch or branch == "HEAD":
            return ""
        success, upstream, _ = self._run_git_sync(
            ['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}']
        )
        if success and upstream.strip():
            return ""
        return branch

    def push(self, remote: str = "origin", branch: str = "", force: bool = False, callback: Callable[[bool, str], None] = None):
        """通过 PrismQML 线程池推送到远程。"""
        self.operationStarted.emit("正在推送...")
        remote = (remote or "").strip()
        branch = (branch or "").strip()

        self.progressUpdated.emit(0, "正在准备推送")

        def work() -> tuple[bool, str]:
            resolved_branch = branch
            remotes = self.get_remotes()
            if remote not in remotes:
                message = (
                    f"未配置远程 '{remote}',请先在「分支」或克隆向导中添加远程仓库"
                    if not remotes
                    else f"远程 '{remote}' 不存在,可用: {', '.join(remotes)}"
                )
                return False, message
            if not resolved_branch:
                resolved_branch = self.get_current_branch()
            if not resolved_branch or resolved_branch == "HEAD":
                return False, "当前没有可推送的分支(空仓库或处于分离头指针状态,请先提交)"
            if self._bad_ref(resolved_branch):
                return False, "非法的分支名"

            args = ['push', '--progress', '-u']
            if force:
                args.append('--force-with-lease')
            args.extend((remote, resolved_branch))
            task = current_task()
            success, _stdout, stderr = self._run_git_push_sync(
                args,
                timeout=60,
                on_progress=lambda percent, message: task.report_progress(
                    (percent, message)
                ),
            )
            return (
                success,
                "推送成功"
                if success
                else self._friendly_git_error(stderr, "推送失败"),
            )

        def finished(result: object) -> None:
            success, message = result
            if success:
                self.progressUpdated.emit(100, "推送完成")
                self.statusChanged.emit()
            self.operationFinished.emit(success, message)
            if callback:
                callback(success, message)

        return submit_to_pool(
            work,
            on_success=finished,
            on_failure=lambda exc: finished((
                False, self._friendly_git_error(str(exc), "推送失败")
            )),
            on_progress=lambda update: self.progressUpdated.emit(
                int(update[0]), str(update[1])
            ),
        )

    def push_with_upstream(self, remote: str = "origin", branch: str = "", callback: Callable[[bool, str], None] = None):
        """兼容入口；``push`` 已统一设置上游。"""
        return self.push(remote, branch, callback=callback)
    
    def set_upstream(self, local_branch: str, remote: str, remote_branch: str) -> tuple[bool, str]:
        """设置分支的上游跟踪关系（同步）
        
        Args:
            local_branch: 本地分支名
            remote: 远程仓库名
            remote_branch: 远程分支名
        
        Returns:
            (success, message)
        """
        local_branch = (local_branch or "").strip()
        remote = (remote or "").strip()
        remote_branch = (remote_branch or "").strip()
        if self._bad_ref(local_branch) or self._bad_ref(remote_branch):
            return False, "非法的分支名"
        if self._bad_ref(remote):
            return False, "非法的远程名"
        if remote not in self.get_remotes():
            return False, f"远程 '{remote}' 不存在"
        args = ['branch', '--set-upstream-to', f'{remote}/{remote_branch}', local_branch]
        success, stdout, stderr = self._run_git_sync(args)
        if success:
            self.statusChanged.emit()
            return True, f"已设置 {local_branch} 跟踪 {remote}/{remote_branch}"
        return False, self._friendly_git_error(stderr, "设置上游分支失败")

    def pull(self, remote: str = "", branch: str = "", rebase: bool = False, callback: Callable[[bool, str], None] = None):
        """通过 PrismQML 线程池拉取远程变更。"""
        self.operationStarted.emit("正在拉取...")
        remote = (remote or "").strip()
        branch = (branch or "").strip()

        def work() -> tuple[bool, str]:
            selected_remote = remote
            selected_branch = branch
            remotes = self.get_remotes()
            if selected_remote and selected_remote not in remotes:
                return False, (
                    f"未配置远程 '{selected_remote}',请先添加远程仓库"
                    if not remotes
                    else f"远程 '{selected_remote}' 不存在,可用: {', '.join(remotes)}"
                )
            if not selected_remote and not remotes:
                return False, "当前仓库没有远程仓库，请先添加远程仓库"
            if selected_branch and not selected_remote:
                return False, "指定分支时还需要选择远程仓库"
            if selected_branch and self._bad_ref(selected_branch):
                return False, "非法的分支名"

            auto_branch = False
            if not selected_branch:
                selected_branch = self._current_branch_without_upstream()
                auto_branch = bool(selected_branch)
                if auto_branch and not selected_remote:
                    selected_remote = (
                        "origin" if "origin" in remotes else remotes[0]
                    )

            args = ['pull']
            if rebase:
                args.append('--rebase')
            if selected_remote:
                args.append(selected_remote)
            if selected_branch:
                args.append(selected_branch)
            success, stdout, stderr = self._run_git_sync(args, timeout=60)
            if success:
                if auto_branch:
                    track_ok, _, _ = self._run_git_sync([
                        'branch', '--set-upstream-to',
                        f'{selected_remote}/{selected_branch}', selected_branch
                    ])
                    if track_ok:
                        return True, (
                            f"拉取成功，已自动关联 {selected_remote}/{selected_branch}；"
                            "以后直接点击“拉取”即可。"
                        )
                    return True, (
                        f"拉取成功，但未能自动关联 {selected_remote}/{selected_branch}；"
                        "下次请在“分支”页设置上游。"
                    )
                return True, "拉取成功"
            detail = "\n".join(
                part.strip()
                for part in (stdout, stderr)
                if part and part.strip()
            )
            if "CONFLICT" in detail or "Automatic merge failed" in detail:
                return False, "拉取产生合并冲突,请到「冲突」页解决"
            return False, self._friendly_git_error(detail, "拉取失败")

        def finished(result: object) -> None:
            success, message = result
            if success:
                self.statusChanged.emit()
            self.operationFinished.emit(success, message)
            if callback:
                callback(success, message)

        return submit_to_pool(
            work,
            on_success=finished,
            on_failure=lambda exc: finished((
                False, self._friendly_git_error(str(exc), "拉取失败")
            )),
        )

    def fetch(self, remote: str = "origin", callback: Callable[[bool, str], None] = None):
        """通过 PrismQML 线程池获取指定远程更新。"""
        self.operationStarted.emit("正在获取远程更新...")
        remote = (remote or "").strip()

        def work() -> tuple[bool, str]:
            if remote not in self.get_remotes():
                return False, f"未配置远程 '{remote}',请先添加远程仓库"
            success, _stdout, stderr = self._run_git_sync(
                ['fetch', '--prune', remote], timeout=60
            )
            return (
                success,
                "获取成功"
                if success
                else self._friendly_git_error(stderr, "获取失败"),
            )

        def finished(result: object) -> None:
            success, message = result
            if success:
                self.statusChanged.emit()
            self.operationFinished.emit(success, message)
            if callback:
                callback(success, message)

        return submit_to_pool(
            work,
            on_success=finished,
            on_failure=lambda exc: finished((
                False, self._friendly_git_error(str(exc), "获取失败")
            )),
        )

    def fetch_all(self, callback: Callable[[bool, str], None] = None):
        """通过 PrismQML 线程池获取全部远程更新。"""
        self.operationStarted.emit("正在获取全部远程更新...")

        def work() -> tuple[bool, str]:
            if not self.get_remotes():
                return False, "未配置远程仓库,请先添加远程仓库"
            success, stdout, stderr = self._run_git_sync(
                ['fetch', '--all', '--prune'], timeout=60
            )
            return (
                success,
                "全部远程更新获取成功"
                if success
                else self._friendly_git_error(
                    stderr or stdout, "获取全部远程更新失败"
                ),
            )

        def finished(result: object) -> None:
            success, message = result
            if success:
                self.statusChanged.emit()
            self.operationFinished.emit(success, message)
            if callback:
                callback(success, message)

        return submit_to_pool(
            work,
            on_success=finished,
            on_failure=lambda exc: finished((
                False,
                self._friendly_git_error(str(exc), "获取全部远程更新失败"),
            )),
        )

    def _resolve_current_upstream(self) -> tuple[bool, str, str, str]:
        """解析当前分支上游 -> (ok, remote, upstream, msg)。"""
        has_head, _, _ = self._run_git_sync(['rev-parse', '--verify', 'HEAD'])
        if not has_head:
            return False, "", "", "当前仓库还没有提交,无法用远程覆盖本地"

        branch = self.get_current_branch()
        if not branch or branch == "HEAD":
            return False, "", "", "当前处于分离头指针状态,无法确定要覆盖的本地分支"

        ok, remote, _ = self._run_git_sync(['config', '--get', f'branch.{branch}.remote'])
        remote = remote.strip()
        if not ok or not remote:
            return False, "", "", "当前分支未设置上游,请先设置跟踪分支"
        if remote not in self.get_remotes():
            return False, "", "", f"上游远程 '{remote}' 不存在,请检查远程配置"

        ok, upstream, _ = self._run_git_sync(
            ['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'])
        upstream = upstream.strip()
        if not ok or not upstream:
            return False, "", "", "当前分支未设置有效上游,请先设置跟踪分支"
        return True, remote, upstream, ""

    def force_reset_to_upstream_sync(self) -> tuple[bool, str]:
        """用当前分支的上游覆盖本地分支。

        等价流程:解析当前分支上游 -> fetch 对应远程 -> reset --hard @{u}。
        该操作会丢弃已跟踪文件的本地改动,并让本地分支回到上游位置。
        """
        ok, remote, upstream, msg = self._resolve_current_upstream()
        if not ok:
            return False, msg

        success, _, stderr = self._run_git_sync(['fetch', remote], timeout=60)
        if not success:
            return False, self._friendly_git_error(stderr, "获取远程更新失败")

        success, _, stderr = self._run_git_sync(['rev-parse', '--verify', '@{u}'])
        if not success:
            return False, self._friendly_git_error(
                stderr, f"上游分支不可用: {upstream}"
            )

        success, _, stderr = self._run_git_sync(['reset', '--hard', '@{u}'])
        if success:
            self.statusChanged.emit()
            return True, f"已用上游 {upstream} 覆盖本地"
        return False, self._friendly_git_error(stderr, "远程覆盖本地失败")

    def force_reset_to_upstream(self, callback: Callable[[bool, str], None] = None):
        """异步执行远程覆盖本地。"""
        def on_finished(result: object) -> None:
            success, msg = result
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)

        self.operationStarted.emit("正在用远程覆盖本地...")
        return submit_to_pool(
            self.force_reset_to_upstream_sync,
            on_success=on_finished,
            on_failure=lambda exc: on_finished((
                False, self._friendly_git_error(str(exc), "远程覆盖本地失败")
            )),
        )

    # ==================== 分支操作 ====================

    @staticmethod
    def _bad_ref(name: str) -> bool:
        """校验 ref 名(分支/标签)是否非法:空、以 - 开头(会被 git 当选项)、含控制字符。
        git ref 命名规范本就不允许以 - 开头,这里提前拦截防注入/误解析。"""
        if not name or name.startswith('-'):
            return True
        # ref 名不能含空格/控制字符/git 特殊序列
        if any(c in name for c in (' ', '\t', '\n', '\r', '~', '^', ':', '?', '*', '[', '\\')):
            return True
        if (
            '..' in name or '@{' in name or '//' in name
            or name.startswith(('/', '.')) or name.endswith(('/', '.'))
            or name.endswith('.lock')
        ):
            return True
        return False

    def _split_configured_remote_branch(
        self, remote_branch: str
    ) -> tuple[str, str]:
        """按已配置远程名拆分 ``remote/branch``，优先匹配最长名称。"""
        for remote in sorted(self.get_remotes(), key=len, reverse=True):
            prefix = f"{remote}/"
            if remote_branch.startswith(prefix):
                return remote, remote_branch[len(prefix):]
        return "", ""

    def checkout_branch(self, branch: str) -> tuple[bool, str]:
        """切换分支"""
        if self._bad_ref(branch):
            return False, "非法的分支名"
        success, stdout, stderr = self._run_git_sync(['checkout', branch])
        if success:
            self.statusChanged.emit()
            return True, f"已切换到分支 {branch}"
        return False, self._friendly_git_error(stderr, "切换分支失败")

    def checkout_remote_branch(self, remote_branch: str, local_branch: str = "") -> tuple[bool, str]:
        """从远程分支创建本地跟踪分支并切换过去。"""
        remote_branch = (remote_branch or "").strip()
        local_branch = (local_branch or "").strip()
        if not local_branch and "/" in remote_branch:
            local_branch = remote_branch.split("/", 1)[1]
        if self._bad_ref(remote_branch) or self._bad_ref(local_branch):
            return False, "非法的分支名"
        ok, stdout, _ = self._run_git_sync(['branch', '-r', '--list', remote_branch])
        if not ok or not stdout.strip():
            return False, f"远程分支不存在: {remote_branch}"
        success, _, stderr = self._run_git_sync(['checkout', '-b', local_branch, '--track', remote_branch])
        if success:
            self.statusChanged.emit()
            return True, f"已检出 {remote_branch} 为本地分支 {local_branch}"
        return False, self._friendly_git_error(stderr, "检出远程分支失败")

    def fetch_and_checkout_remote_branch(
        self, remote_branch: str, local_branch: str = ""
    ) -> tuple[bool, str]:
        """获取指定远程后，创建并切换到对应的本地跟踪分支。"""
        remote_branch = (remote_branch or "").strip()
        local_branch = (local_branch or "").strip()
        remote, branch = self._split_configured_remote_branch(remote_branch)
        if not remote:
            return False, f"未配置远程分支所属远程: {remote_branch}"
        if not local_branch:
            local_branch = branch
        if self._bad_ref(branch) or self._bad_ref(local_branch):
            return False, "非法的分支名"
        fetched, stdout, stderr = self._run_git_sync(
            ['fetch', '--prune', remote], timeout=60
        )
        if not fetched:
            return False, self._friendly_git_error(
                stderr or stdout, "获取远程分支失败"
            )
        exists, _, _ = self._run_git_sync([
            'show-ref', '--verify', '--quiet',
            f'refs/remotes/{remote}/{branch}',
        ])
        if not exists:
            self.statusChanged.emit()
            return False, f"获取完成，但远程分支不存在: {remote}/{branch}"
        success, _, error = self._run_git_sync([
            'checkout', '-b', local_branch, '--track', f'{remote}/{branch}'
        ])
        self.statusChanged.emit()
        if success:
            return True, f"已获取并检出 {remote}/{branch} 为本地分支 {local_branch}"
        return False, self._friendly_git_error(error, "检出远程分支失败")

    def create_branch(
        self,
        branch: str,
        checkout: bool = True,
        start_point: str = "HEAD",
    ) -> tuple[bool, str]:
        """从指定提交起点创建分支，可选择是否切换过去。"""
        branch = (branch or "").strip()
        start_point = (start_point or "HEAD").strip()
        if self._bad_ref(branch):
            return False, "非法的分支名"
        if self._bad_ref(start_point):
            return False, "非法的分支起点"

        resolved, commit_hash, error = self._run_git_sync(
            ['rev-parse', '--verify', f'{start_point}^{{commit}}']
        )
        if not resolved:
            # 保留空仓库原有的“创建并切换到未出生分支”能力；
            # 不切换时 Git 尚无提交可供创建实际分支引用，仍明确报错。
            if start_point == "HEAD" and checkout:
                success, _, stderr = self._run_git_sync(
                    ['checkout', '-b', branch]
                )
                if success:
                    self.statusChanged.emit()
                    return True, f"已创建并切换到分支 {branch}（空仓库）"
                return False, self._friendly_git_error(
                    stderr, "创建分支失败", branch_name=branch
                )
            return False, self._friendly_git_error(
                error, f"分支起点不存在或不是提交: {start_point}"
            )
        commit_hash = commit_hash.strip()
        if not commit_hash:
            return False, f"无法解析分支起点: {start_point}"

        if checkout:
            success, _, stderr = self._run_git_sync(
                ['checkout', '-b', branch, commit_hash]
            )
        else:
            success, _, stderr = self._run_git_sync(
                ['branch', branch, commit_hash]
            )

        if success:
            self.statusChanged.emit()
            action = "已创建并切换到" if checkout else "已创建"
            return True, f"{action}分支 {branch}（起点 {start_point}）"
        return False, self._friendly_git_error(
            stderr, "创建分支失败", branch_name=branch
        )

    def delete_branch(self, branch: str, force: bool = False) -> tuple[bool, str]:
        """删除分支"""
        if self._bad_ref(branch):
            return False, "非法的分支名"
        if branch == self.get_current_branch():
            return False, "不能删除当前所在分支,请先切换到其他分支"
        args = ['branch', '-D' if force else '-d', branch]
        success, stdout, stderr = self._run_git_sync(args)
        if success:
            self.statusChanged.emit()
            return True, f"已删除分支 {branch}"
        return False, self._friendly_git_error(stderr, "删除分支失败")

    def delete_remote_branch(self, remote_branch: str) -> tuple[bool, str]:
        """删除完整远程跟踪名对应的远程分支，保留本地分支。"""
        remote_branch = (remote_branch or "").strip()
        remote = ""
        branch = ""
        for candidate in sorted(self.get_remotes(), key=len, reverse=True):
            prefix = f"{candidate}/"
            if remote_branch.startswith(prefix):
                remote = candidate
                branch = remote_branch[len(prefix):]
                break

        if not remote:
            return False, f"未配置远程分支所属远程: {remote_branch}"
        if self._bad_ref(branch):
            return False, "非法的远程分支名"

        success, _, stderr = self._run_git_sync(
            ['push', remote, '--delete', f'refs/heads/{branch}'],
            timeout=300,
        )
        if success:
            self.statusChanged.emit()
            return True, f"已删除远程分支 {remote}/{branch}"
        return False, self._friendly_git_error(
            stderr, f"删除远程分支失败: {remote}/{branch}"
        )

    def rename_branch(self, old_name: str, new_name: str) -> tuple[bool, str]:
        """重命名本地分支。"""
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if self._bad_ref(old_name) or self._bad_ref(new_name):
            return False, "非法的分支名"
        success, _, stderr = self._run_git_sync(['branch', '-m', old_name, new_name])
        if success:
            self.statusChanged.emit()
            return True, f"已重命名分支 {old_name} -> {new_name}"
        return False, self._friendly_git_error(stderr, "重命名分支失败")

    def rebase_onto(self, branch: str) -> tuple[bool, str]:
        """将当前分支 rebase 到目标分支。"""
        branch = (branch or "").strip()
        if self._bad_ref(branch):
            return False, "非法的分支名"
        success, _, stderr = self._run_git_sync(['rebase', branch])
        if success:
            self.statusChanged.emit()
            return True, f"已 rebase 到 {branch}"
        if self.get_operation_state() == "rebase":
            self.statusChanged.emit()
            return False, (
                self._friendly_git_error(stderr, "Rebase 产生冲突")
                + "\n请在冲突页解决后继续、跳过或中止 rebase"
            )
        return False, self._friendly_git_error(stderr, "Rebase 失败")

    def merge_branch(self, branch: str, callback: Callable[[bool, str], None] = None):
        """合并分支（异步）"""
        if self._bad_ref(branch):
            self.operationFinished.emit(False, "非法的分支名")
            if callback:
                callback(False, "非法的分支名")
            return
        self.operationStarted.emit(f"正在合并分支 {branch}...")
        
        def on_finished(success: bool, stdout: str, stderr: str):
            if success:
                self.statusChanged.emit()
            msg = (
                f"已合并分支 {branch}"
                if success
                else self._friendly_git_error(
                    "\n".join(
                        part.strip()
                        for part in (stdout, stderr)
                        if part and part.strip()
                    ),
                    "合并分支失败",
                )
            )
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
        if not commit_hash or not commit_hash.strip():
            return False, "未指定提交"
        success, stdout, stderr = self._run_git_sync(['revert', '--no-edit', commit_hash])
        if success:
            self.statusChanged.emit()
            return True, f"已撤销提交 {commit_hash[:7]}（创建了新的撤销提交）"
        if self.get_operation_state() == "revert":
            self.statusChanged.emit()
            return False, (
                self._friendly_git_error(stderr, "Revert 产生冲突")
                + "\n请在冲突页解决后继续或中止 revert"
            )
        return False, self._friendly_git_error(stderr, "撤销提交失败")

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
        if not commit_hash or not commit_hash.strip():
            return False, "未指定目标提交"

        success, stdout, stderr = self._run_git_sync(['reset', f'--{mode}', commit_hash])
        if success:
            self.statusChanged.emit()
            mode_desc = {
                "soft": "HEAD 已移动,改动保留在暂存区和工作区",
                "mixed": "HEAD 已移动,保留工作区改动,清空暂存区",
                "hard": "已完全回滚,丢弃所有改动"
            }
            return True, f"已回滚到 {commit_hash[:7]}（{mode_desc[mode]}）"
        return False, self._friendly_git_error(stderr, "回滚失败")

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
        # 异步执行所有步骤
        def do_quick_commit_push():
            """在 PrismQML 线程池执行所有 Git 操作。"""
            task = current_task()

            def report(percent: int, message: str) -> None:
                task.report_progress((percent, message))

            has_committed = False
            
            # 步骤1：检查是否有变更需要暂存
            changes = self.get_status()
            has_unstaged = any(not c.staged for c in changes)
            has_staged = any(c.staged for c in changes)
            
            # 步骤2：如果有未暂存的变更，暂存所有
            if has_unstaged:
                report(10, "暂存所有变更...")
                staged_ok, stage_msg = self._stage_all_result()
                if not staged_ok:
                    return False, stage_msg
                has_staged = True  # 暂存后就有已暂存的了
            
            # 步骤3：如果有已暂存的变更，提交
            if has_staged:
                report(33, "提交变更...")
                success, commit_msg = self.commit(message)
                if not success:
                    return False, commit_msg
                has_committed = True
            
            # 步骤4：检查远程仓库
            remotes = self.get_remotes()
            if not remotes:
                if has_committed:
                    return True, "提交成功，但没有配置远程仓库"
                else:
                    return False, "没有变更需要提交，也没有配置远程仓库"
            
            # 步骤5：推送（同步执行）
            report(66, "推送到远程...")
            current_branch = self.get_current_branch()
            args = ['push', '--progress', '-u', 'origin', current_branch]

            def emit_push_progress(percent: int, detail: str) -> None:
                overall = 66 + round(percent * 0.33)
                report(overall, detail)

            success, stdout, stderr = self._run_git_push_sync(
                args, timeout=60, on_progress=emit_push_progress
            )
            
            if success:
                report(100, "完成")
                if has_committed:
                    return True, "一键提交推送成功"
                else:
                    return True, "推送成功（无新提交）"
            else:
                return False, f"推送失败: {self._friendly_git_error(stderr, '未知错误')}"
        
        def on_finished(result: object) -> None:
            success, msg = result
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        # 提交到引擎任务池前先通知界面进入操作状态。
        self.operationStarted.emit("正在执行一键提交推送...")
        self.progressUpdated.emit(0, "正在检查变更")

        def report_progress(update: object) -> None:
            percent, detail = update
            self.progressUpdated.emit(int(percent), str(detail))

        return submit_to_pool(
            do_quick_commit_push,
            on_success=on_finished,
            on_failure=lambda exc: on_finished((
                False, self._friendly_git_error(str(exc), "一键提交推送失败")
            )),
            on_progress=report_progress,
        )

    # ==================== 冲突处理 ====================

    def get_conflicts(self) -> list[ConflictInfo]:
        """获取冲突文件列表"""
        conflicts = []

        # 直接解析 porcelain:冲突文件状态码为 DD/AU/UD/UA/DU/AA/UU(含 U,或双 A/D)
        # 不能用 get_status(它对 XY 双状态位各 append 一次,冲突文件 UU 会被列两遍)
        success, stdout, _ = self._run_git_sync(['status', '--porcelain=v1'])
        if not success:
            return []

        conflict_codes = {"DD", "AU", "UD", "UA", "DU", "AA", "UU"}
        seen = set()
        for line in stdout.split('\n'):
            if len(conflicts) >= MAX_CONFLICT_RESULTS:
                break
            if len(line) < 3:
                continue
            xy = line[:2]
            if xy not in conflict_codes:
                continue
            path = line[3:].rstrip('\r\n')
            if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
                path = path[1:-1]
            if path in seen:
                continue
            seen.add(path)

            conflict = ConflictInfo(path=path)
            try:
                full_path = os.path.join(self._repo_path, path)
                real_path = os.path.realpath(full_path)
                repo_real_path = os.path.realpath(self._repo_path)
                if not real_path.startswith(repo_real_path + os.sep):
                    continue
                if os.path.exists(real_path):
                    if os.path.getsize(real_path) > 1024 * 1024:
                        conflicts.append(conflict)
                        continue
                    with open(real_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(1024 * 100)
                        if '<<<<<<<' in content and '>>>>>>>' in content:
                            conflict.has_conflict_markers = True
            except Exception as e:
                logger.debug(f"读取冲突文件失败 {path}: {e}")

            conflicts.append(conflict)
            if len(conflicts) >= MAX_CONFLICT_RESULTS:
                break
        
        return conflicts

    def _resolve_conflicts(
        self, file_paths: list[str], side: str
    ) -> tuple[bool, str]:
        """用指定一侧逐个解决并暂存冲突，最后只发送一次状态刷新。"""
        if side not in {"ours", "theirs"}:
            return False, "不支持的冲突解决策略"
        if not file_paths:
            return False, "当前没有需要解决的冲突文件"

        resolved = 0
        failures: list[str] = []
        for file_path in file_paths:
            checkout_ok, checkout_stdout, checkout_stderr = self._run_git_sync(
                ['checkout', f'--{side}', '--', file_path]
            )
            if not checkout_ok:
                failures.append(self._friendly_git_error(
                    checkout_stderr or checkout_stdout,
                    f"解决冲突失败: {file_path}",
                ))
                continue
            stage_ok, stage_stdout, stage_stderr = self._run_git_sync(
                ['add', '--', file_path]
            )
            if not stage_ok:
                failures.append(self._friendly_git_error(
                    stage_stderr or stage_stdout,
                    f"暂存解决结果失败: {file_path}",
                ))
                continue
            resolved += 1

        if resolved:
            self.statusChanged.emit()
        side_text = "本地" if side == "ours" else "远程"
        if failures:
            return False, (
                f"已按{side_text}版本解决 {resolved}/{len(file_paths)} 个冲突；"
                f"{failures[0]}"
            )
        return True, f"已按{side_text}版本解决 {resolved} 个冲突"

    def resolve_conflict_with_ours(self, file_path: str) -> tuple[bool, str]:
        """采用本地版本解决单个冲突(--ours)。"""
        return self._resolve_conflicts([file_path], "ours")

    def resolve_conflict_with_theirs(self, file_path: str) -> tuple[bool, str]:
        """采用远程版本解决单个冲突(--theirs)。"""
        return self._resolve_conflicts([file_path], "theirs")

    def resolve_all_conflicts_with_ours(self) -> tuple[bool, str]:
        """采用本地版本解决当前全部冲突。"""
        return self._resolve_conflicts(
            [conflict.path for conflict in self.get_conflicts()], "ours"
        )

    def resolve_all_conflicts_with_theirs(self) -> tuple[bool, str]:
        """采用远程版本解决当前全部冲突。"""
        return self._resolve_conflicts(
            [conflict.path for conflict in self.get_conflicts()], "theirs"
        )

    def abort_merge(self) -> tuple[bool, str]:
        """中止合并操作"""
        success, stdout, stderr = self._run_git_sync(['merge', '--abort'])
        if success:
            self.statusChanged.emit()
            return True, "已中止合并"
        return False, self._friendly_git_error(stderr, "中止合并失败")

    def _git_path(self, name: str) -> str:
        """返回 Git 内部路径,兼容 worktree 的 .git 文件形态。"""
        if not self._repo_path:
            return ""
        success, stdout, _ = self._run_git_sync(['rev-parse', '--git-path', name])
        if success and stdout.strip():
            path = stdout.strip()
            if not os.path.isabs(path):
                path = os.path.join(self._repo_path, path)
            return path
        return os.path.join(self._repo_path, '.git', name)

    def _git_marker_exists(self, name: str) -> bool:
        path = self._git_path(name)
        return bool(path and os.path.exists(path))

    def get_operation_state(self) -> str:
        """当前中途 Git 操作: merge/rebase/cherry-pick/revert,无则返回空字符串。"""
        if not self._repo_path:
            return ""
        if self._git_marker_exists('rebase-merge') or self._git_marker_exists('rebase-apply'):
            return "rebase"
        if self._git_marker_exists('CHERRY_PICK_HEAD'):
            return "cherry-pick"
        if self._git_marker_exists('REVERT_HEAD'):
            return "revert"
        if self._git_marker_exists('MERGE_HEAD'):
            return "merge"
        return ""

    def _run_mid_operation(self, operation: str, args: list[str], success_msg: str, failure_msg: str) -> tuple[bool, str]:
        if self.get_operation_state() != operation:
            return False, f"当前不在 {operation} 中途状态"
        success, _, stderr = self._run_git_sync(args)
        self.statusChanged.emit()
        if success:
            return True, success_msg
        return False, self._friendly_git_error(stderr, failure_msg)

    def continue_merge(self) -> tuple[bool, str]:
        """使用已有合并消息完成已解决冲突的 merge。"""
        return self._run_mid_operation(
            "merge",
            ['-c', 'core.editor=true', 'merge', '--continue'],
            "合并已完成",
            "完成合并失败",
        )

    def continue_rebase(self) -> tuple[bool, str]:
        """继续 rebase。"""
        return self._run_mid_operation(
            "rebase",
            ['-c', 'core.editor=true', 'rebase', '--continue'],
            "已继续 rebase",
            "继续 rebase 失败",
        )

    def abort_rebase(self) -> tuple[bool, str]:
        """中止 rebase。"""
        return self._run_mid_operation(
            "rebase",
            ['rebase', '--abort'],
            "已中止 rebase",
            "中止 rebase 失败",
        )

    def skip_rebase(self) -> tuple[bool, str]:
        """跳过当前 rebase 补丁。"""
        return self._run_mid_operation(
            "rebase",
            ['rebase', '--skip'],
            "已跳过当前 rebase 补丁",
            "跳过 rebase 补丁失败",
        )

    def continue_cherry_pick(self) -> tuple[bool, str]:
        """继续 cherry-pick。"""
        return self._run_mid_operation(
            "cherry-pick",
            ['-c', 'core.editor=true', 'cherry-pick', '--continue'],
            "已继续 cherry-pick",
            "继续 cherry-pick 失败",
        )

    def abort_cherry_pick(self) -> tuple[bool, str]:
        """中止 cherry-pick。"""
        return self._run_mid_operation(
            "cherry-pick",
            ['cherry-pick', '--abort'],
            "已中止 cherry-pick",
            "中止 cherry-pick 失败",
        )

    def continue_revert(self) -> tuple[bool, str]:
        """继续 revert。"""
        return self._run_mid_operation(
            "revert",
            ['-c', 'core.editor=true', 'revert', '--continue'],
            "已继续 revert",
            "继续 revert 失败",
        )

    def abort_revert(self) -> tuple[bool, str]:
        """中止 revert。"""
        return self._run_mid_operation(
            "revert",
            ['revert', '--abort'],
            "已中止 revert",
            "中止 revert 失败",
        )

    def is_merging(self) -> bool:
        """检查是否正在合并"""
        return self.get_operation_state() == "merge"

    # ==================== Stash暂存 ====================

    @staticmethod
    def _bad_stash_id(stash_id: str) -> bool:
        if not stash_id or stash_id.startswith('-'):
            return True
        return any(c in stash_id for c in ('\n', '\r', '\t', '\x00'))

    def stash_save(self, message: str = "", include_untracked: bool = False, keep_index: bool = False) -> tuple[bool, str]:
        """暂存当前变更到stash"""
        args = ['stash', 'push']
        if include_untracked:
            args.append('--include-untracked')
        if keep_index:
            args.append('--keep-index')
        if message:
            args.extend(['-m', message])

        success, stdout, stderr = self._run_git_sync(args)
        if success:
            self.statusChanged.emit()
            return True, "已暂存变更到stash"
        return False, self._friendly_git_error(stderr, "暂存失败")

    def stash_list(self) -> list[tuple[str, str]]:
        """获取stash列表
        
        Returns:
            list of (stash_id, message)
        """
        success, stdout, stderr = self._run_git_sync(
            ['stash', 'list', f'-{MAX_STASH_RESULTS}']
        )
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
        
        return stashes[:MAX_STASH_RESULTS]

    def stash_pop(self, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """恢复stash并删除"""
        if self._bad_stash_id(stash_id):
            return False, "非法的 stash 引用"
        if not self.stash_list():
            return False, "没有可恢复的暂存"
        success, stdout, stderr = self._run_git_sync(['stash', 'pop', stash_id])
        if success:
            self.statusChanged.emit()
            return True, f"已恢复stash: {stash_id}"
        return False, self._friendly_git_error(stderr, "恢复stash失败")

    def stash_apply(self, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """恢复stash但不删除"""
        if self._bad_stash_id(stash_id):
            return False, "非法的 stash 引用"
        if not self.stash_list():
            return False, "没有可应用的暂存"
        success, stdout, stderr = self._run_git_sync(['stash', 'apply', stash_id])
        if success:
            self.statusChanged.emit()
            return True, f"已应用stash: {stash_id}"
        return False, self._friendly_git_error(stderr, "应用stash失败")

    def stash_drop(self, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """删除指定stash"""
        if self._bad_stash_id(stash_id):
            return False, "非法的 stash 引用"
        success, stdout, stderr = self._run_git_sync(['stash', 'drop', stash_id])
        if success:
            self.statusChanged.emit()
            return True, f"已删除stash: {stash_id}"
        return False, self._friendly_git_error(stderr, "删除stash失败")

    def stash_clear(self) -> tuple[bool, str]:
        """清空所有stash"""
        success, stdout, stderr = self._run_git_sync(['stash', 'clear'])
        if success:
            self.statusChanged.emit()
            return True, "已清空所有stash"
        return False, self._friendly_git_error(stderr, "清空stash失败")

    def stash_show(self, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """查看 stash 内容(diffstat + patch)。"""
        if self._bad_stash_id(stash_id):
            return False, "非法的 stash 引用"
        success, stdout, stderr = self._run_git_sync([
            'stash', 'show', '--stat', '--patch', '--include-untracked', stash_id
        ])
        if success:
            max_size = 200 * 1024
            if len(stdout) > max_size:
                stdout = stdout[:max_size] + "\n\n[内容过大,已截断]"
            return True, stdout or "该 stash 没有可显示的内容"
        return False, self._friendly_git_error(stderr, "查看 stash 失败")

    def stash_branch(self, branch: str, stash_id: str = "stash@{0}") -> tuple[bool, str]:
        """从 stash 创建并切换到新分支。"""
        branch = (branch or "").strip()
        if self._bad_ref(branch):
            return False, "非法的分支名"
        if self._bad_stash_id(stash_id):
            return False, "非法的 stash 引用"
        success, stdout, stderr = self._run_git_sync(['stash', 'branch', branch, stash_id])
        if success:
            self.statusChanged.emit()
            return True, f"已从 {stash_id} 创建分支 {branch}"
        return False, self._friendly_git_error(stderr, "从 stash 创建分支失败")

    # ==================== 文件历史 ====================

    def get_file_history(self, file_path: str, count: int = 50) -> list[CommitInfo]:
        """获取指定文件的提交历史"""
        safe_count = min(max(0, count), MAX_FILE_HISTORY_RESULTS)
        if safe_count == 0:
            return []
        format_str = '%H|%h|%an|%ae|%ad|%s'
        cmd = [
            'log',
            f'-{safe_count}',
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
        
        return commits[:MAX_FILE_HISTORY_RESULTS]

    def get_file_content_at_commit(self, file_path: str, commit_hash: str) -> str:
        """获取文件在指定提交的内容"""
        if not self._path_in_repo(file_path):
            return ""
        success, stdout, stderr = self._run_git_sync(['show', f'{commit_hash}:{file_path}'])
        if not success:
            return ""
        content, _truncated = self._truncate_display_text(
            stdout, MAX_FILE_CONTENT_SIZE
        )
        return content

    def diff_file_between_commits(self, file_path: str, commit1: str, commit2: str) -> str:
        """对比文件在两个提交之间的差异"""
        if not self._path_in_repo(file_path):
            return ""
        success, stdout, _ = self._run_git_sync(['diff', commit1, commit2, '--', file_path])
        if not success:
            return ""
        diff, _truncated = self._truncate_display_text(
            stdout, MAX_COMMIT_DIFF_SIZE
        )
        return diff

    # ==================== Tag标签管理 ====================

    def get_tags(self) -> list[tuple[str, str, str]]:
        """获取Tag列表

        Returns:
            list of (tag_name, commit_hash, message)
        """
        return self.get_tags_at(self._repo_path or "")

    def get_tags_at(self, repo_path: str) -> list[tuple[str, str, str]]:
        """获取指定仓库快照路径的 Tag 列表,避免异步切仓库串读。"""
        success, stdout, _ = self._run_git_sync_at(repo_path, [
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

        return tags[:MAX_TAG_RESULTS]

    def create_tag(
        self,
        name: str,
        message: str = "",
        commit: str = "HEAD",
        annotated: bool | None = None,
    ) -> tuple[bool, str]:
        """创建Tag

        Args:
            name: Tag名称
            message: Tag消息
            commit: 目标提交（默认HEAD）
            annotated: 是否创建附注 Tag;None 时保持旧行为:有消息则附注,否则轻量
        """
        if self._bad_ref(name):
            return False, "非法的标签名"
        if annotated is None:
            annotated = bool(message)
        if annotated:
            # 附注Tag
            args = ['tag', '-a', name, '-m', message, commit]
        else:
            # 轻量级Tag
            args = ['tag', name, commit]

        success, _, stderr = self._run_git_sync(args)
        if success:
            return True, f"已创建Tag: {name}"
        return False, self._friendly_git_error(stderr, "创建Tag失败")

    def delete_tag(self, name: str) -> tuple[bool, str]:
        """删除本地Tag"""
        if self._bad_ref(name):
            return False, "非法的标签名"
        success, _, stderr = self._run_git_sync(['tag', '-d', name])
        if success:
            return True, f"已删除Tag: {name}"
        return False, self._friendly_git_error(stderr, "删除Tag失败")

    def delete_remote_tag(self, name: str, remote: str = "origin") -> tuple[bool, str]:
        """删除远程Tag"""
        if self._bad_ref(name):
            return False, "非法的标签名"
        if remote not in self.get_remotes():
            return False, f"未配置远程 '{remote}'"
        success, _, stderr = self._run_git_sync(['push', remote, '--delete', f'refs/tags/{name}'])
        if success:
            return True, f"已删除远程Tag: {name}"
        return False, self._friendly_git_error(stderr, "删除远程Tag失败")

    def push_tag(self, name: str, remote: str = "origin") -> tuple[bool, str]:
        """推送Tag到远程"""
        if self._bad_ref(name):
            return False, "非法的标签名"
        if remote not in self.get_remotes():
            return False, f"未配置远程 '{remote}',请先添加远程仓库"
        success, _, stderr = self._run_git_push_sync(
            ['push', '--progress', remote, name], timeout=120
        )
        if success:
            self.progressUpdated.emit(100, "推送标签完成")
            return True, f"已推送Tag: {name}"
        return False, self._friendly_git_error(stderr, "推送Tag失败")

    def push_all_tags(self, remote: str = "origin") -> tuple[bool, str]:
        """推送所有Tag到远程"""
        if remote not in self.get_remotes():
            return False, f"未配置远程 '{remote}',请先添加远程仓库"
        success, _, stderr = self._run_git_push_sync(
            ['push', '--progress', remote, '--tags'], timeout=120
        )
        if success:
            self.progressUpdated.emit(100, "推送标签完成")
            return True, "已推送所有Tag"
        return False, self._friendly_git_error(stderr, "推送Tag失败")

    def checkout_tag(self, name: str) -> tuple[bool, str]:
        """切换到Tag（分离头指针状态）"""
        if self._bad_ref(name):
            return False, "非法的标签名"
        success, _, stderr = self._run_git_sync(['checkout', name])
        if success:
            self.statusChanged.emit()
            return True, f"已切换到Tag: {name}"
        return False, self._friendly_git_error(stderr, "切换Tag失败")

    # ==================== 高级 Git 功能 ====================

    @staticmethod
    def _bad_revision_arg(rev: str) -> bool:
        if not rev or rev.startswith('-'):
            return True
        return any(c in rev for c in (' ', '\t', '\n', '\r', '\x00'))

    def list_worktrees(self) -> list[WorktreeInfo]:
        """列出当前仓库关联的 worktree。"""
        return self.list_worktrees_at(self._repo_path or "")

    def list_worktrees_at(self, repo_path: str) -> list[WorktreeInfo]:
        """列出指定仓库快照关联的 worktree，避免异步切仓库时串读。"""
        success, stdout, _ = self._run_git_sync_at(
            repo_path,
            ['worktree', 'list', '--porcelain'],
        )
        if not success:
            return []

        items: list[WorktreeInfo] = []
        current: dict[str, object] = {}

        def flush() -> None:
            if not current:
                return
            branch = str(current.get("branch", ""))
            if branch.startswith("refs/heads/"):
                branch = branch[len("refs/heads/"):]
            items.append(WorktreeInfo(
                path=str(current.get("path", "")),
                head=str(current.get("head", "")),
                branch=branch,
                detached=bool(current.get("detached", False)),
                bare=bool(current.get("bare", False)),
                prunable=bool(current.get("prunable", False)),
                prunable_reason=str(current.get("prunable_reason", "")),
                locked=bool(current.get("locked", False)),
                locked_reason=str(current.get("locked_reason", "")),
            ))
            current.clear()

        for line in stdout.splitlines():
            if not line:
                flush()
                continue
            if line.startswith("worktree "):
                flush()
                current["path"] = line[len("worktree "):]
            elif line.startswith("HEAD "):
                current["head"] = line[len("HEAD "):]
            elif line.startswith("branch "):
                current["branch"] = line[len("branch "):]
            elif line == "detached":
                current["detached"] = True
            elif line == "bare":
                current["bare"] = True
            elif line.startswith("prunable"):
                current["prunable"] = True
                current["prunable_reason"] = line[len("prunable"):].strip()
            elif line.startswith("locked"):
                current["locked"] = True
                current["locked_reason"] = line[len("locked"):].strip()
        flush()
        return items

    def add_worktree(self, path: str, branch: str = "", create_branch: bool = False) -> tuple[bool, str]:
        """添加 worktree。"""
        path = (path or "").strip()
        branch = (branch or "").strip()
        if not path:
            return False, "未指定 worktree 路径"
        if branch and self._bad_ref(branch):
            return False, "非法的分支名"
        if create_branch and not branch:
            return False, "创建新分支时必须填写分支名"

        args = ['worktree', 'add']
        if create_branch:
            args.extend(['-b', branch, path])
        else:
            args.append(path)
            if branch:
                args.append(branch)
        success, _, stderr = self._run_git_sync(args, timeout=120)
        if success:
            self.statusChanged.emit()
            return True, f"已添加 worktree: {path}"
        return False, self._friendly_git_error(stderr, "添加 worktree 失败")

    def remove_worktree(self, path: str, force: bool = False) -> tuple[bool, str]:
        """移除 worktree。"""
        return self.remove_worktree_at(self._repo_path or "", path, force)

    def remove_worktree_at(
        self, repo_path: str, path: str, force: bool = False
    ) -> tuple[bool, str]:
        """使用发起操作时的仓库快照移除 worktree。"""
        path = (path or "").strip()
        if not path:
            return False, "未指定 worktree 路径"
        if force:
            return self._force_remove_detached_worktree_at(repo_path, path)
        args = ['worktree', 'remove']
        args.append(path)
        success, _, stderr = self._run_git_sync_at(repo_path, args, timeout=120)
        if success:
            self.statusChanged.emit()
            return True, f"已移除 worktree: {path}"
        return False, self._friendly_git_error(stderr, "移除 worktree 失败")

    def prune_worktrees(self) -> tuple[bool, str]:
        """清理失效 worktree 记录。"""
        success, _, stderr = self._run_git_sync(['worktree', 'prune'])
        if success:
            self.statusChanged.emit()
            return True, "已清理失效 worktree 记录"
        return False, self._friendly_git_error(stderr, "清理 worktree 失败")

    @staticmethod
    def _worktree_path_key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path))

    def _force_remove_candidate_at(
        self, repo_path: str, path: str
    ) -> tuple[Optional[WorktreeInfo], str]:
        """返回可强制移除的 detached linked worktree 与拒绝原因。"""
        worktrees = self.list_worktrees_at(repo_path)
        if not worktrees:
            return None, "无法读取当前仓库的 worktree 列表"

        target_key = self._worktree_path_key(path)
        primary_key = self._worktree_path_key(worktrees[0].path)
        if target_key in (primary_key, self._worktree_path_key(repo_path)):
            return None, "不能强制删除当前工作树或主工作树"

        target = next(
            (item for item in worktrees[1:]
             if self._worktree_path_key(item.path) == target_key),
            None,
        )
        if target is None:
            return None, "目标已不是当前仓库登记的关联工作树，请刷新后重试"
        if not target.detached:
            return None, "只能强制删除游离工作树；分支工作树请先按普通方式处理"
        if target.locked:
            return None, "该工作树已锁定，请先确认没有任务使用它，再解除锁定后重试。"
        if target.prunable or not os.path.isdir(target.path):
            return None, "工作树目录已失效，请改用“清理失效记录”"
        return target, ""

    def _force_remove_detached_worktree_at(
        self, repo_path: str, path: str
    ) -> tuple[bool, str]:
        """实时核验并强制移除仓库快照登记的 detached linked worktree。"""
        target, error = self._force_remove_candidate_at(repo_path, path)
        if target is None:
            return False, error
        success, _, stderr = self._run_git_sync_at(
            repo_path,
            ['worktree', 'remove', '--force', target.path],
            timeout=120,
        )
        if not success:
            return False, self._friendly_git_error(stderr, "强制删除工作树失败")
        self.statusChanged.emit()
        return True, f"已强制删除游离工作树: {target.path}"

    def _worktree_cleanup_readiness(
        self, worktree: WorktreeInfo
    ) -> tuple[str, str]:
        """返回 (ready/skip/error, reason)，不改变工作树。"""
        if worktree.prunable or not os.path.isdir(worktree.path):
            return "skip", "目录不存在，请先清理失效记录"
        if worktree.locked:
            return "skip", "工作树已锁定"
        success, stdout, stderr = self._run_git_sync_at(
            worktree.path,
            ['status', '--porcelain=v1', '-z', '--untracked-files=normal'],
            timeout=60,
        )
        if not success:
            return "error", self._friendly_git_error(stderr, "读取工作树状态失败")
        if stdout:
            return "skip", "存在未提交修改或未跟踪文件"
        return "ready", ""

    def preview_detached_worktree_cleanup_at(
        self, repo_path: str
    ) -> tuple[bool, list[str], list[tuple[str, str]], str]:
        """预览可安全移除的 detached linked worktree。"""
        worktrees = self.list_worktrees_at(repo_path)
        if not worktrees:
            return False, [], [], "无法读取当前仓库的 worktree 列表"
        removable: list[str] = []
        skipped: list[tuple[str, str]] = []
        for worktree in worktrees[1:]:
            if not worktree.detached:
                continue
            state, reason = self._worktree_cleanup_readiness(worktree)
            if state == "ready":
                removable.append(worktree.path)
            else:
                skipped.append((worktree.path, reason))
        return True, removable, skipped, ""

    def _remove_detached_worktree_candidate(
        self, repo_path: str, worktree: WorktreeInfo
    ) -> tuple[str, str]:
        state, reason = self._worktree_cleanup_readiness(worktree)
        if state != "ready":
            return state, reason
        success, _, stderr = self._run_git_sync_at(
            repo_path,
            ['worktree', 'remove', worktree.path],
            timeout=120,
        )
        if success:
            return "removed", ""
        return "error", self._friendly_git_error(stderr, "移除工作树失败")

    def remove_detached_worktrees_at(
        self, repo_path: str, requested_paths: list[str]
    ) -> tuple[bool, str]:
        """重新核验并移除指定的干净 detached linked worktree。"""
        worktrees = self.list_worktrees_at(repo_path)
        if not worktrees:
            return False, "无法读取当前仓库的 worktree 列表"
        candidates = {
            self._worktree_path_key(worktree.path): worktree
            for worktree in worktrees[1:]
            if worktree.detached
        }
        removed = 0
        skipped: list[str] = []
        failures: list[str] = []
        seen: set[str] = set()
        for path in requested_paths:
            key = self._worktree_path_key(str(path))
            if key in seen:
                continue
            seen.add(key)
            worktree = candidates.get(key)
            if worktree is None:
                skipped.append(f"{path}: 已不是可清理的游离工作树")
                continue
            state, reason = self._remove_detached_worktree_candidate(repo_path, worktree)
            if state == "removed":
                removed += 1
            elif state == "skip":
                skipped.append(f"{worktree.path}: {reason}")
            else:
                failures.append(f"{worktree.path}: {reason}")
                logger.warning("批量移除游离工作树失败 %s: %s", worktree.path, reason)

        if removed:
            self.statusChanged.emit()
        details = [f"已移除 {removed} 个游离工作树"]
        if skipped:
            details.append(f"跳过 {len(skipped)} 个有改动、锁定或已失效项")
        if failures:
            details.append(f"{len(failures)} 个移除失败")
        return not failures, "；".join(details)

    def list_submodules(self) -> list[SubmoduleInfo]:
        """列出 submodule 状态。"""
        return self.list_submodules_at(self._repo_path or "")

    def list_submodules_at(self, repo_path: str) -> list[SubmoduleInfo]:
        """列出指定仓库快照的 submodule 状态，避免异步切仓库时串读。"""
        success, stdout, _ = self._run_git_sync_at(
            repo_path,
            ['submodule', 'status', '--recursive'],
        )
        if not success or not stdout.strip():
            return []

        status_text = {
            ' ': "正常",
            '-': "未初始化",
            '+': "提交不一致",
            'U': "冲突",
        }
        modules: list[SubmoduleInfo] = []
        for line in stdout.splitlines():
            if not line:
                continue
            flag = line[0]
            rest = line[1:].strip()
            parts = rest.split(None, 2)
            if len(parts) < 2:
                continue
            modules.append(SubmoduleInfo(
                path=parts[1],
                hash=parts[0],
                status=status_text.get(flag, "未知"),
                description=parts[2] if len(parts) > 2 else "",
            ))
        return modules

    def submodule_update(self, init: bool = True, recursive: bool = True) -> tuple[bool, str]:
        """初始化/更新 submodule。"""
        args = ['submodule', 'update']
        if init:
            args.append('--init')
        if recursive:
            args.append('--recursive')
        success, _, stderr = self._run_git_sync(args, timeout=300)
        if success:
            self.statusChanged.emit()
            return True, "Submodule 已更新"
        return False, self._friendly_git_error(stderr, "更新 submodule 失败")

    def submodule_sync(self, recursive: bool = True) -> tuple[bool, str]:
        """同步 submodule URL 配置。"""
        args = ['submodule', 'sync']
        if recursive:
            args.append('--recursive')
        success, _, stderr = self._run_git_sync(args, timeout=120)
        if success:
            return True, "Submodule URL 已同步"
        return False, self._friendly_git_error(stderr, "同步 submodule 失败")

    def lfs_status(self) -> tuple[bool, str]:
        """获取 Git LFS 状态。"""
        success, stdout, stderr = self._run_git_sync(['lfs', 'status'])
        if success:
            return True, "Git LFS status:\n" + (stdout or "当前没有 LFS 状态输出")
        return False, self._friendly_git_error(
            stderr, "Git LFS 不可用或当前仓库未初始化 LFS"
        )

    def lfs_pull(self) -> tuple[bool, str]:
        """拉取 Git LFS 对象。"""
        success, stdout, stderr = self._run_git_sync(['lfs', 'pull'], timeout=300)
        if success:
            self.statusChanged.emit()
            return True, stdout or "Git LFS pull 完成"
        return False, self._friendly_git_error(stderr, "Git LFS pull 失败")

    def lfs_push(self, remote: str = "origin", branch: str = "HEAD") -> tuple[bool, str]:
        """推送 Git LFS 对象。"""
        remote = (remote or "").strip()
        branch = (branch or "").strip()
        if self._bad_ref(remote):
            return False, "非法的远程名"
        if self._bad_revision_arg(branch):
            return False, "非法的分支或修订名"
        success, stdout, stderr = self._run_git_sync(['lfs', 'push', remote, branch], timeout=300)
        if success:
            return True, stdout or "Git LFS push 完成"
        return False, self._friendly_git_error(stderr, "Git LFS push 失败")

    def is_bisecting(self) -> bool:
        return self._git_marker_exists('BISECT_LOG')

    def bisect_start(self, good_rev: str, bad_rev: str = "HEAD") -> tuple[bool, str]:
        """开始 bisect。"""
        good_rev = (good_rev or "").strip()
        bad_rev = (bad_rev or "HEAD").strip()
        if self._bad_revision_arg(good_rev) or self._bad_revision_arg(bad_rev):
            return False, "非法的 good/bad 修订名"
        success, stdout, stderr = self._run_git_sync(['bisect', 'start', bad_rev, good_rev])
        if success:
            self.statusChanged.emit()
            return True, stdout or "Bisect 已开始"
        return False, self._friendly_git_error(stderr, "开始 bisect 失败")

    def bisect_good(self, rev: str = "") -> tuple[bool, str]:
        return self._bisect_mark("good", rev)

    def bisect_bad(self, rev: str = "") -> tuple[bool, str]:
        return self._bisect_mark("bad", rev)

    def bisect_skip(self, rev: str = "") -> tuple[bool, str]:
        return self._bisect_mark("skip", rev)

    def _bisect_mark(self, mark: str, rev: str = "") -> tuple[bool, str]:
        if not self.is_bisecting():
            return False, "当前没有 bisect 会话"
        rev = (rev or "").strip()
        if rev and self._bad_revision_arg(rev):
            return False, "非法的修订名"
        args = ['bisect', mark]
        if rev:
            args.append(rev)
        success, stdout, stderr = self._run_git_sync(args)
        self.statusChanged.emit()
        if success:
            return True, stdout or f"Bisect {mark} 已记录"
        return False, self._friendly_git_error(stderr, f"Bisect {mark} 失败")

    def bisect_reset(self) -> tuple[bool, str]:
        """结束 bisect 并回到原分支。"""
        success, stdout, stderr = self._run_git_sync(['bisect', 'reset'])
        if success:
            self.statusChanged.emit()
            return True, stdout or "Bisect 已结束"
        return False, self._friendly_git_error(stderr, "结束 bisect 失败")

    def bisect_log(self) -> tuple[bool, str]:
        """读取 bisect 日志。"""
        if not self.is_bisecting():
            return True, "当前没有 bisect 会话"
        success, stdout, stderr = self._run_git_sync(['bisect', 'log'])
        if success:
            return True, stdout or "Bisect 日志为空"
        return False, self._friendly_git_error(stderr, "读取 bisect 日志失败")

    # ==================== 远程仓库管理 ====================

    @staticmethod
    def _bad_url(url: str) -> bool:
        """校验远程 URL 协议安全:只允许常见安全协议,拒绝 ext::/fd::/file:// 等
        可执行命令或读本地文件的危险传输。"""
        if not url or url.startswith('-'):
            return True
        u = url.strip().lower()
        # git 的危险传输助手:ext::(执行任意命令)、fd::、file://(读本地)
        for bad in ('ext::', 'fd::', 'file://'):
            if u.startswith(bad):
                return True
        # 允许:http(s)://、git://、ssh://、scp 风格 user@host:path
        if u.startswith(('http://', 'https://', 'git://', 'ssh://')):
            return False
        if '@' in url and ':' in url.split('@', 1)[1]:  # git@host:path
            return False
        return True  # 其他一律拒绝(含裸本地路径,克隆本地仓库走文件选择器另说)

    def add_remote(self, name: str, url: str) -> tuple[bool, str]:
        """添加远程仓库"""
        if self._bad_ref(name):
            return False, "非法的远程名"
        if self._bad_url(url):
            return False, "不支持或不安全的远程地址"
        success, _, stderr = self._run_git_sync(['remote', 'add', name, url])
        if success:
            return True, f"已添加远程仓库: {name}"
        return False, self._friendly_git_error(stderr, "添加远程仓库失败")

    def remove_remote(self, name: str) -> tuple[bool, str]:
        """删除远程仓库"""
        if self._bad_ref(name):
            return False, "非法的远程名"
        success, _, stderr = self._run_git_sync(['remote', 'remove', name])
        if success:
            return True, f"已删除远程仓库: {name}"
        return False, self._friendly_git_error(stderr, "删除远程仓库失败")

    def set_remote_url(self, name: str, url: str) -> tuple[bool, str]:
        """修改远程URL"""
        if self._bad_ref(name):
            return False, "非法的远程名"
        if self._bad_url(url):
            return False, "不支持或不安全的远程地址"
        success, _, stderr = self._run_git_sync(['remote', 'set-url', name, url])
        if success:
            return True, f"已修改远程URL: {name}"
        return False, self._friendly_git_error(stderr, "修改远程URL失败")

    def rename_remote(self, old_name: str, new_name: str) -> tuple[bool, str]:
        """重命名远程仓库配置。"""
        old_name = (old_name or "").strip()
        new_name = (new_name or "").strip()
        if self._bad_ref(old_name) or self._bad_ref(new_name):
            return False, "非法的远程名"
        success, _, stderr = self._run_git_sync(['remote', 'rename', old_name, new_name])
        if success:
            self.statusChanged.emit()
            return True, f"已重命名远程 {old_name} -> {new_name}"
        return False, self._friendly_git_error(stderr, "重命名远程失败")

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

    @staticmethod
    def _parse_commit_file_output(
        stdout: str, limit: int | None = None
    ) -> tuple[list[FileChange], int, dict[str, int]]:
        files: list[FileChange] = []
        total = 0
        status_counts: dict[str, int] = {}
        safe_limit = None if limit is None else max(0, limit)
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('\t', 1)
            if len(parts) != 2:
                continue
            total += 1
            status_char = parts[0][0]
            status_counts[status_char] = status_counts.get(status_char, 0) + 1
            if safe_limit is not None and len(files) >= safe_limit:
                continue
            file_path = parts[1]
            files.append(
                FileChange(
                    path=file_path,
                    status=GitService._parse_status_char_static(status_char),
                    staged=False,
                )
            )
        return files, total, status_counts

    @staticmethod
    def _parse_status_char_static(char: str) -> FileStatus:
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

    def get_commit_files(self, commit_hash: str) -> list[FileChange]:
        """获取提交的完整变更文件列表(供非 UI 调用)。"""
        success, stdout, _ = self._run_git_sync([
            'diff-tree', '--root', '--no-commit-id', '--name-status', '-r', commit_hash
        ])
        if not success:
            return []
        files, _total, _status_counts = self._parse_commit_file_output(stdout)
        return files

    def get_commit_files_preview(
        self,
        commit_hash: str,
        limit: int = MAX_COMMIT_FILE_PREVIEW,
    ) -> tuple[list[FileChange], int, bool, dict[str, int]]:
        """获取有界的提交文件预览及总数。"""
        success, stdout, _ = self._run_git_sync([
            'diff-tree', '--root', '--no-commit-id', '--name-status', '-r', commit_hash
        ])
        if not success:
            return [], 0, False, {}
        safe_limit = min(max(0, limit), MAX_COMMIT_FILE_PREVIEW)
        files, total, status_counts = self._parse_commit_file_output(
            stdout, safe_limit
        )
        return files, total, total > len(files), status_counts

    @staticmethod
    def _truncate_display_text(
        text: str, limit: int = MAX_COMMIT_DIFF_SIZE
    ) -> tuple[str, bool]:
        encoded = text.encode("utf-8")
        if len(encoded) <= limit:
            return text, False
        marker = "\n\n[内容过大，已截断]"
        marker_size = len(marker.encode("utf-8"))
        prefix = encoded[:max(0, limit - marker_size)].decode(
            "utf-8", errors="ignore"
        )
        return prefix + marker, True

    def get_commit_diff(
        self, commit_hash: str, file_path: str | None = None
    ) -> str:
        """获取有界提交 diff，可选按文件过滤。"""
        args = ['show', '--format=', commit_hash]
        if file_path:
            if '\t' in file_path:
                file_path = file_path.rsplit('\t', 1)[-1]
            if not self._path_in_repo(file_path):
                return ""
            args.extend(['--', file_path])
        success, stdout, _ = self._run_git_sync(args)
        if not success:
            return ""
        diff, _truncated = self._truncate_display_text(stdout.lstrip('\n'))
        return diff

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
            commit = CommitInfo(
                hash=parts[0],
                short_hash=parts[1],
                author=parts[2],
                email=parts[3],
                date=parts[4],
                message=parts[5] + ('\n' + parts[6] if len(parts) == 7 else '')
            )
            commit.message, _truncated = self._truncate_display_text(
                commit.message, MAX_FILE_CONTENT_SIZE
            )
            return self._mark_reverted_commits_at(self._repo_path or "", [commit])[0]
        return None

    # ==================== Cherry-pick ====================

    def cherry_pick(self, commit_hash: str) -> tuple[bool, str]:
        """应用指定提交到当前分支"""
        if not commit_hash or not commit_hash.strip():
            return False, "未指定提交"
        success, stdout, stderr = self._run_git_sync(['cherry-pick', '--no-edit', commit_hash])
        if success:
            self.statusChanged.emit()
            return True, f"已应用提交 {commit_hash[:7]}"
        if self.get_operation_state() == "cherry-pick":
            self.statusChanged.emit()
            return False, (
                self._friendly_git_error(stderr, "Cherry-pick 产生冲突")
                + "\n请在冲突页解决后继续或中止 cherry-pick"
            )
        return False, self._friendly_git_error(stderr, "Cherry-pick失败")

    def cherry_pick_to_branch(
        self, commit_hash: str, target_branch: str
    ) -> tuple[bool, str]:
        """将指定提交应用到明确的本地目标分支。"""
        commit_hash = (commit_hash or "").strip()
        target_branch = (target_branch or "").strip()
        if not commit_hash:
            return False, "未指定提交"
        if self._bad_ref(target_branch):
            return False, "非法的目标分支名"

        branch_exists, _, _ = self._run_git_sync([
            'show-ref', '--verify', '--quiet', f'refs/heads/{target_branch}'
        ])
        if not branch_exists:
            return False, f"目标分支不存在: {target_branch}"

        current_branch = self.get_current_branch()
        if current_branch != target_branch:
            switched, switch_msg = self.checkout_branch(target_branch)
            if not switched:
                return False, f"无法切换到目标分支“{target_branch}”: {switch_msg}"

        ok, message = self.cherry_pick(commit_hash)
        if ok:
            return True, f"已将提交 {commit_hash[:7]} 应用到分支 {target_branch}"
        return False, message

    # ==================== 克隆仓库 ====================

    def clone(self, url: str, path: str, callback: Callable[[bool, str], None] = None):
        """克隆远程仓库（异步）
        
        Args:
            url: 远程仓库URL
            path: 本地路径
            callback: 完成回调
        """
        if self._bad_url(url):
            self.operationFinished.emit(False, "不支持或不安全的远程地址")
            if callback:
                callback(False, "不支持或不安全的远程地址")
            return
        self.operationStarted.emit("正在克隆仓库...")

        parent_dir = os.path.dirname(os.path.abspath(path)) or os.getcwd()
        if not os.path.isdir(parent_dir):
            msg = f"目标目录的父路径不存在: {parent_dir}"
            self.operationFinished.emit(False, msg)
            if callback:
                callback(False, msg)
            return

        args = ['clone', url, path, '--progress']
        
        def on_finished(success: bool, stdout: str, stderr: str):
            if success:
                msg = f"克隆成功: {path}"
            else:
                msg = self._friendly_git_error(stderr, "克隆失败")
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        # 克隆可能很慢，设置较长超时
        self._run_git_async(args, on_finished, timeout=300, cwd=parent_dir)
    
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
                encoding='utf-8',
                errors='replace',
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                return True, f"已初始化Git仓库: {path}"
            return False, self._friendly_git_error(result.stderr, "初始化失败")
        except Exception as e:
            logger.exception(f"初始化 Git 仓库失败: path={path}, error={e}")
            return False, "初始化失败，请检查目录权限与 Git 安装状态后重试。"

    # ==================== Rebase操作 ====================

    # ==================== Reflog引用日志 ====================

    def get_reflog(self, count: int = 50) -> list[tuple[str, str, str]]:
        """获取引用日志
        
        Returns:
            list of (hash, ref, message)
        """
        safe_count = min(max(0, count), MAX_REFLOG_RESULTS)
        if safe_count == 0:
            return []
        success, stdout, _ = self._run_git_sync(
            ['reflog', f'-{safe_count}', '--format=%H|%gd|%gs']
        )
        if not success:
            return []
        
        logs = []
        for line in stdout.strip().split('\n'):
            if not line:
                continue
            parts = line.split('|', 2)
            if len(parts) == 3:
                logs.append((parts[0], parts[1], parts[2]))
        
        return logs[:MAX_REFLOG_RESULTS]

    # ==================== Blame代码作者 ====================

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

    def clean_preview_limited(
        self, limit: int = MAX_CLEAN_PREVIEW
    ) -> tuple[list[str], int, bool]:
        """获取有界清理预览及总数。"""
        success, stdout, _ = self._run_git_sync(['clean', '-n', '-d'])
        if not success:
            return [], 0, False
        safe_limit = min(max(0, limit), MAX_CLEAN_PREVIEW)
        files: list[str] = []
        total = 0
        for line in stdout.strip().split('\n'):
            if not line.startswith('Would remove '):
                continue
            total += 1
            if len(files) < safe_limit:
                files.append(line[13:])
        return files, total, total > len(files)

    def clean(self, include_directories: bool = True) -> tuple[bool, str]:
        """清理未跟踪文件（危险操作）"""
        args = ['clean', '-f']
        if include_directories:
            args.append('-d')
        
        success, stdout, stderr = self._run_git_sync(args)
        if success:
            self.statusChanged.emit()
            return True, "已清理未跟踪文件"
        return False, self._friendly_git_error(stderr, "清理失败")

    # ==================== Config配置 ====================

    def _run_git_config_sync(self, args: list[str], global_scope: bool, timeout: int = 30) -> tuple[bool, str, str]:
        """执行 Git 配置命令;全局配置不要求当前已打开仓库。"""
        if self._repo_path:
            return self._run_git_sync(args, timeout)
        if global_scope:
            return self._run_git_sync_at(str(Path.home()), args, timeout)
        return False, "", "未设置仓库路径"

    def get_config(self, key: str, global_scope: bool = False) -> str:
        """获取Git配置"""
        args = ['config']
        if global_scope:
            args.append('--global')
        args.append(key)

        success, stdout, _ = self._run_git_config_sync(args, global_scope)
        return stdout.strip() if success else ""

    def set_config(self, key: str, value: str, global_scope: bool = False) -> tuple[bool, str]:
        """设置Git配置"""
        args = ['config']
        if global_scope:
            args.append('--global')
        args.extend([key, value])

        success, _, stderr = self._run_git_config_sync(args, global_scope)
        if success:
            return True, f"已设置 {key} = {value}"
        return False, self._friendly_git_error(stderr, "设置配置失败")

    def get_user_info(self, global_scope: bool = False) -> tuple[str, str]:
        """获取用户信息

        Returns:
            (name, email)
        """
        name = self.get_config('user.name', global_scope)
        email = self.get_config('user.email', global_scope)
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
        return False, self._friendly_git_error(stderr, "清理失败")

    # ==================== 其他实用命令 ====================

    def gc(self, callback: Callable[[bool, str], None] = None):
        """垃圾回收，优化仓库（异步）"""
        self.operationStarted.emit("正在优化仓库...")
        
        def on_finished(success: bool, stdout: str, stderr: str):
            msg = (
                "仓库优化完成"
                if success
                else self._friendly_git_error(stderr, "优化失败")
            )
            self.operationFinished.emit(success, msg)
            if callback:
                callback(success, msg)
        
        self._run_git_async(['gc', '--auto'], on_finished, timeout=60)


# 全局单例
gitService = GitService()
