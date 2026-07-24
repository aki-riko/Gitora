# coding: utf-8
"""
GitBridge - GitService 的 QML 对接壳

设计原则(只重构对接层):
- 组合持有一个 GitService 实例，不复制 Git 命令逻辑。
- 负责 dataclass(FileChange/CommitInfo/...) -> QML 可消费的 dict/list 转换。
- 阻塞型查询和操作统一提交到 PrismQML 任务池；QML 只接收 TaskHandle 或完成信号。
"""
import os
import tempfile
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional

from PySide6.QtCore import QObject, Slot, Signal, Property

from app.common.git_service import (
    GitService, FileChange, CommitInfo, BranchInfo, ConflictInfo,
    WorktreeInfo, SubmoduleInfo, DiffFile,
)
from app.common.logger import get_logger
from app.common.prism_task import submit_to_pool
from app_qml.backend.file_change_model import FileChangeListModel

logger = get_logger("GitBridge")


def _file_change_to_dict(fc: FileChange) -> dict:
    """FileChange dataclass -> QML 友好 dict"""
    return {
        "path": fc.path,
        "status": fc.status.value,       # 单字符,如 "M"/"A"/"?"
        "statusText": fc.status_text,    # 本地化文本,如 "已修改"
        "staged": fc.staged,
    }


def _commit_to_dict(c: CommitInfo) -> dict:
    """CommitInfo dataclass -> QML 友好 dict"""
    return {
        "hash": c.hash,
        "shortHash": c.short_hash,
        "author": c.author,
        "email": c.email,
        "date": c.date,
        "message": c.message,
        "branch": getattr(c, "branch", ""),
        "revertedBy": getattr(c, "reverted_by", ""),
        "reverts": getattr(c, "reverts", ""),
        "parents": list(getattr(c, "parents", [])),
        "refs": [
            {"name": ref.name, "kind": ref.kind}
            for ref in getattr(c, "refs", [])
        ],
        "graph": _graph_row_to_dict(getattr(c, "graph", None)),
        "graphHeader": _graph_header_to_dict(getattr(c, "graph", None)),
    }


def _graph_segment_to_dict(segment) -> dict:
    return {
        "fromLane": segment.from_lane,
        "toLane": segment.to_lane,
        "colorIndex": segment.color_index,
        "startAtNode": segment.start_at_node,
        "endAtNode": segment.end_at_node,
    }


def _graph_row_to_dict(row) -> dict:
    if row is None:
        return {}
    return {
        "nodeLane": row.node_lane,
        "nodeColorIndex": row.node_color_index,
        "laneCount": row.lane_count,
        "segments": [_graph_segment_to_dict(segment) for segment in row.segments],
    }


def _graph_header_to_dict(row) -> dict:
    if row is None:
        return {}
    return {
        "segments": [
            _graph_segment_to_dict(segment)
            for segment in row.header_segments
        ]
    }


def _branch_to_dict(b: BranchInfo) -> dict:
    """BranchInfo dataclass -> QML 友好 dict"""
    return {
        "name": b.name,
        "isCurrent": b.is_current,
        "isRemote": b.is_remote,
        "tracking": b.tracking,
        "ahead": b.ahead,
        "behind": b.behind,
    }


def _conflict_to_dict(c: ConflictInfo) -> dict:
    """ConflictInfo dataclass -> QML 友好 dict"""
    return {
        "path": c.path,
        "oursContent": c.ours_content,
        "theirsContent": c.theirs_content,
        "baseContent": c.base_content,
        "hasConflictMarkers": c.has_conflict_markers,
    }


def _worktree_to_dict(w: WorktreeInfo) -> dict:
    return {
        "path": w.path,
        "head": w.head,
        "shortHead": w.head[:7] if w.head else "",
        "branch": w.branch,
        "detached": w.detached,
        "bare": w.bare,
        "prunable": w.prunable,
        "prunableReason": w.prunable_reason,
    }


def _submodule_to_dict(s: SubmoduleInfo) -> dict:
    return {
        "path": s.path,
        "hash": s.hash,
        "shortHash": s.hash[:7] if s.hash else "",
        "status": s.status,
        "description": s.description,
    }


def _diff_file_to_dict(d: DiffFile) -> dict:
    return {
        "path": d.path,
        "oldPath": d.old_path,
        "newPath": d.new_path,
        "status": d.status,
        "additions": d.additions,
        "deletions": d.deletions,
        "hunkCount": len(d.hunks),
    }


class GitBridge(QObject):
    """暴露给 QML 的 Git 后端门面"""

    # 规则文件只允许仓库根目录下的这两个固定文件，避免把任意路径写入
    # 的能力暴露给 QML。
    _REPO_RULE_FILES = frozenset({".gitignore", ".gitattributes"})

    # 透传 GitService 的信号(QML 直接 onXxx 连接)
    statusChanged = Signal()
    operationStarted = Signal(str)
    operationFinished = Signal(bool, str)
    quickCommitPushFinished = Signal(bool, str)
    progressUpdated = Signal(int, str)
    repoPathChanged = Signal(str)
    repoOpened = Signal(bool, str)   # 异步打开完成(成功, 路径/错误消息)
    statusReady = Signal(str, int)              # 后台状态就绪(repoPath, 变更数量)
    branchReady = Signal(str, str)             # 后台当前分支就绪(repoPath, 分支)
    logReady = Signal(str, int, "QVariantList")    # 后台提交分页就绪(repoPath, skip, 批次)
    searchReady = Signal(str, "QVariantList")       # 后台搜索结果就绪(repoPath, 结果)
    # 以下为耗时操作异步化新增信号(均带请求参数供前端校验防过期)
    diffReady = Signal(str, str, bool, str)              # (repoPath, path, staged, diff内容)
    commitDiffReady = Signal(str, str, str)              # (repoPath, hash, diff)
    branchesReady = Signal(str, "QVariantList")          # (repoPath, 分支列表)
    tagsReady = Signal(str, "QVariantList")              # (repoPath, 标签列表)
    fileHistoryReady = Signal(str, str, "QVariantList")  # (repoPath, path, 提交列表)
    conflictsReady = Signal(str, "QVariantList")         # (repoPath, 冲突文件列表)
    conflictStateReady = Signal(str, str)                 # (repoPath, 操作类型)
    commitFilesReady = Signal(str, str, "QVariantList")  # (repoPath, hash, 文件列表)
    fileContentReady = Signal(str, str, str, str)        # (repoPath, path, hash, 内容)
    diffBetweenReady = Signal(str, str, str, str, str)   # (repoPath, path, c1, c2, diff)
    stashListReady = Signal(str, "QVariantList")         # (repoPath, stash 列表)
    cleanPreviewReady = Signal(str, "QVariantList")      # (repoPath, 待清理文件列表)
    reflogReady = Signal(str, "QVariantList")            # (repoPath, reflog 列表)
    advancedStateReady = Signal(str, "QVariantList", "QVariantList")  # (repoPath, worktree, submodule)
    # 外部变化轮询间隔(ms):覆盖命令行/其他 Git 工具引起的状态变化
    _POLL_INTERVAL_MS = 2000

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._svc = GitService(self)
        self._file_change_model = FileChangeListModel(self)
        # ---- 外部变化轮询 ----
        # 定期计算仓库状态指纹,变了就 emit statusChanged,让所有视图统一刷新。
        # 内部 Git 操作本身也会发 statusChanged；每次内部信号都让旧基线失效，
        # 避免下一轮把同一变化再次误判为“外部变化”。generation 用于丢弃
        # 变更发生前已经在后台计算的过期结果。
        self._poll_fingerprint = ""     # 上次指纹(基线)
        self._poll_busy = False         # 本轮是否在算
        self._poll_repo = ""            # 本轮针对的仓库(防切仓库串读)
        self._poll_generation = 0       # 基线代际(内部变更/切仓库时递增)
        # 转发底层信号
        self._svc.statusChanged.connect(self._forward_service_status_changed)
        self._svc.operationStarted.connect(self.operationStarted)
        self._svc.operationFinished.connect(self.operationFinished)
        self._svc.progressUpdated.connect(self.progressUpdated)
        self._log_request_serial = 0
        self._search_request_serial = 0
        self._tags_request_serial = 0
        self._advanced_request_serial = 0
        self._open_request_serial = 0

        # 指纹计算放后台线程(跑 git 命令,不能阻塞主线程);
        # 用 _poll_busy 防重入,避免上一轮未完又起一轮。
        # QTimer 在主线程排队;emit 信号跨线程安全(排队回主线程)
        from PySide6.QtCore import QTimer
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_tick)
        self._poll_timer.start()

    def _submit_query(
        self,
        function: Callable[[], Any],
        *,
        label: str,
        on_success: Callable[[Any], None] | None = None,
        on_failure: Callable[[BaseException], None] | None = None,
    ):
        """把只读查询提交给 PrismQML；所有回调都由引擎排回主线程。"""
        def failed(exc: BaseException) -> None:
            logger.warning(f"{label}失败: {type(exc).__name__}: {exc}")
            if on_failure is not None:
                on_failure(exc)

        return submit_to_pool(
            function,
            on_success=on_success,
            on_failure=failed,
        )

    def _submit_operation(
        self,
        description: str,
        function: Callable[[], tuple[bool, str]],
        *,
        publish: bool = True,
    ):
        """提交一个返回 ``(成功, 消息)`` 的 Git 操作。"""
        if publish:
            self.operationStarted.emit(description)

        def succeeded(result: object) -> None:
            try:
                ok, message = result
            except (TypeError, ValueError):
                logger.error(f"Git 后台操作返回值无效: {result!r}")
                if publish:
                    self.operationFinished.emit(False, "Git 操作返回值无效")
                return
            if publish:
                self.operationFinished.emit(bool(ok), str(message))

        def failed(exc: BaseException) -> None:
            logger.warning(
                f"Git 后台操作异常: {type(exc).__name__}: {exc}"
            )
            if publish:
                self.operationFinished.emit(
                    False,
                    "Git 操作发生异常，请重试；技术详情已记录到日志。",
                )

        return submit_to_pool(
            function,
            on_success=succeeded,
            on_failure=failed,
        )

    def _reset_poll_baseline(self):
        """使当前基线失效；下一轮只建新基线，不重复发刷新。"""
        self._poll_generation += 1
        self._poll_fingerprint = ""
        self._poll_repo = self._svc.repo_path or ""

    @Slot()
    def _forward_service_status_changed(self):
        """转发内部变更一次，并阻止轮询把同一变化再转发一次。"""
        self._reset_poll_baseline()
        self.statusChanged.emit()

    def _poll_tick(self):
        """定时器回调(主线程):把指纹计算交给 PrismQML 线程池。"""
        repo = self._svc.repo_path or ""
        if not repo or self._poll_busy:
            return
        self._poll_busy = True
        self._poll_repo = repo
        generation = self._poll_generation
        self._submit_query(
            lambda: self._svc.compute_state_fingerprint(repo),
            label="计算状态指纹",
            on_success=lambda fp: self._on_fingerprint_ready(
                repo, str(fp), generation
            ),
            on_failure=lambda _exc: self._on_fingerprint_ready(
                repo, "", generation
            ),
        )

    def _on_fingerprint_ready(self, repo: str, fp: str, generation: int):
        """指纹算完（主线程回调）：与基线比较并刷新。"""
        # 仓库已切走或内部操作已使基线换代 → 丢弃过期结果。
        if (
            generation != self._poll_generation
            or repo != (self._svc.repo_path or "")
        ):
            self._poll_busy = False
            return
        if fp == "":
            # 读取失败/仓库无效:不更新基线也不触发,等下一轮
            self._poll_busy = False
            return
        if self._poll_fingerprint == "":
            # 首次:仅建立基线,不触发(打开仓库已各视图各自 reload 过)
            self._poll_fingerprint = fp
        elif fp != self._poll_fingerprint:
            self._poll_fingerprint = fp
            self.statusChanged.emit()
        self._poll_busy = False

    # ==================== 属性 ====================
    @Property(str, notify=repoPathChanged)
    def repoPath(self) -> str:
        return self._svc.repo_path or ""

    @property
    def service(self) -> GitService:
        """供同进程后端组件复用同一个仓库会话，不暴露给 QML。"""
        return self._svc

    @Property(QObject, constant=True)
    def fileChangeModel(self) -> FileChangeListModel:
        return self._file_change_model

    @Property(int, constant=True)
    def pollIntervalMs(self) -> int:
        """供需要页面级探查的视图复用统一轮询间隔。"""
        return self._POLL_INTERVAL_MS

    # ==================== 仓库 ====================
    def setRepoPath(self, path: str) -> bool:
        """仅供 Python 测试/内部启动使用；QML 必须调用 ``openRepoAsync``。"""
        ok = self._svc.set_repo_path(path, emit_status=False)
        if ok:
            from app.common.recent_repos import recentReposManager
            recentReposManager.add(self._svc.repo_path or path)
            self._reset_poll_baseline()
            self.repoPathChanged.emit(self._svc.repo_path or "")
        return ok

    @Slot(str)
    def openRepoAsync(self, path: str):
        """后台打开仓库,不阻塞主线程;成功时由 repoPathChanged 驱动各视图刷新。"""
        self._open_request_serial += 1
        request_serial = self._open_request_serial

        def completed(ok: object) -> None:
            if request_serial != self._open_request_serial:
                return
            if ok:
                self._svc.activate_repo_path(path, emit_status=False)
                from app.common.recent_repos import recentReposManager
                recentReposManager.add(self._svc.repo_path or path)
                self._reset_poll_baseline()
                self.repoPathChanged.emit(self._svc.repo_path or "")
                self.repoOpened.emit(True, self._svc.repo_path or path)
            else:
                self.repoOpened.emit(False, path)

        return self._submit_query(
            lambda: self._svc.validate_repo_path(path),
            label=f"打开仓库 {path}",
            on_success=completed,
            on_failure=lambda _exc: completed(False),
        )

    @Slot(result="QVariantList")
    def getRecentRepos(self) -> list:
        """最近打开的仓库 -> [path, ...]"""
        from app.common.recent_repos import recentReposManager
        return recentReposManager.get_all()

    @Slot(str)
    def removeRecentRepo(self, path: str):
        from app.common.recent_repos import recentReposManager
        recentReposManager.remove(path)

    @Slot()
    def clearRecentRepos(self):
        from app.common.recent_repos import recentReposManager
        recentReposManager.clear()

    # ==================== 状态 ====================

    @Slot(str, object, str)
    def _apply_status_result(self, repo: str, changes: list[FileChange], branch: str):
        """在 GUI 线程批量更新模型，并丢弃切仓库后的过期结果。"""
        if repo != (self._svc.repo_path or ""):
            return
        self._file_change_model.replace(changes)
        self.statusReady.emit(repo, len(changes))
        self.branchReady.emit(repo, branch)

    @Slot()
    def requestStatus(self):
        """后台获取状态，回到 GUI 线程批量刷新 fileChangeModel。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: (
                self._svc.get_status_at(repo),
                self._svc.get_current_branch_at(repo),
            ),
            label="获取仓库状态",
            on_success=lambda result: self._apply_status_result(
                repo, result[0], result[1]
            ),
            on_failure=lambda _exc: self._apply_status_result(repo, [], ""),
        )

    @Slot(result=QObject)
    def getCurrentBranch(self):
        """异步读取当前分支，返回 PrismQML ``TaskHandle``。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: self._svc.get_current_branch_at(repo),
            label="获取当前分支",
        )

    # ==================== 仓库维护 ====================
    @Slot()
    def requestCleanPreview(self):
        """后台预览待清理文件,完成发 cleanPreviewReady(repoPath,list)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            self._svc.clean_preview,
            label="预览待清理文件",
            on_success=lambda data: self.cleanPreviewReady.emit(repo, data),
            on_failure=lambda _exc: self.cleanPreviewReady.emit(repo, []),
        )

    @Slot(bool, result=QObject)
    def clean(self, include_directories: bool):
        """异步清理未跟踪文件。"""
        return self._submit_operation(
            "正在清理未跟踪文件...",
            lambda: self._svc.clean(include_directories=include_directories),
        )

    @Slot()
    def gc(self):
        """垃圾回收(异步);结果经 operationStarted/operationFinished 信号回传"""
        self._svc.gc()

    # ==================== 高级 Git ====================
    @Slot()
    def requestAdvancedState(self):
        """后台读取 worktree/submodule，避免切仓库时阻塞 QML 主线程。"""
        repo = self._svc.repo_path or ""
        self._advanced_request_serial += 1
        request_serial = self._advanced_request_serial

        def work():
            return (
                [
                    _worktree_to_dict(w) for w in self._svc.list_worktrees_at(repo)
                ],
                [
                    _submodule_to_dict(s) for s in self._svc.list_submodules_at(repo)
                ],
            )

        def completed(result: object) -> None:
            if request_serial != self._advanced_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            worktrees, submodules = result
            self.advancedStateReady.emit(repo, worktrees, submodules)

        return self._submit_query(
            work,
            label="获取高级仓库状态",
            on_success=completed,
            on_failure=lambda _exc: completed(([], [])),
        )

    def getWorktrees(self) -> list:
        return [_worktree_to_dict(w) for w in self._svc.list_worktrees()]

    @Slot(str, str, bool, result=QObject)
    def addWorktree(self, path: str, branch: str, create_branch: bool):
        return self._submit_operation(
            "正在添加工作树...",
            lambda: self._svc.add_worktree(path, branch, create_branch),
        )

    @Slot(str, bool, result=QObject)
    def removeWorktree(self, path: str, force: bool):
        return self._submit_operation(
            "正在移除工作树...",
            lambda: self._svc.remove_worktree(path, force),
        )

    @Slot(result=QObject)
    def pruneWorktrees(self):
        return self._submit_operation(
            "正在清理失效工作树...", self._svc.prune_worktrees
        )

    def getSubmodules(self) -> list:
        return [_submodule_to_dict(s) for s in self._svc.list_submodules()]

    @Slot(bool, bool, result=QObject)
    def submoduleUpdate(self, init: bool, recursive: bool):
        return self._submit_operation(
            "正在更新子模块...",
            lambda: self._svc.submodule_update(init, recursive),
        )

    @Slot(bool, result=QObject)
    def submoduleSync(self, recursive: bool):
        return self._submit_operation(
            "正在同步子模块配置...",
            lambda: self._svc.submodule_sync(recursive),
        )

    @Slot(result=QObject)
    def lfsStatus(self):
        return self._submit_operation("正在读取 Git LFS 状态...", self._svc.lfs_status)

    @Slot()
    def lfsPull(self):
        return self._submit_operation(
            "正在拉取 Git LFS 对象...", self._svc.lfs_pull
        )

    @Slot(str, str)
    def lfsPush(self, remote: str, branch: str):
        return self._submit_operation(
            f"正在推送 Git LFS 对象到 {remote} {branch}...",
            lambda: self._svc.lfs_push(remote, branch),
        )

    @Slot(str, str, result=QObject)
    def bisectStart(self, good_rev: str, bad_rev: str):
        return self._submit_operation(
            "正在开始二分定位...",
            lambda: self._svc.bisect_start(good_rev, bad_rev),
        )

    @Slot(str, result=QObject)
    def bisectGood(self, rev: str):
        return self._submit_operation(
            "正在标记正常提交...", lambda: self._svc.bisect_good(rev)
        )

    @Slot(str, result=QObject)
    def bisectBad(self, rev: str):
        return self._submit_operation(
            "正在标记异常提交...", lambda: self._svc.bisect_bad(rev)
        )

    @Slot(str, result=QObject)
    def bisectSkip(self, rev: str):
        return self._submit_operation(
            "正在跳过二分提交...", lambda: self._svc.bisect_skip(rev)
        )

    @Slot(result=QObject)
    def bisectReset(self):
        return self._submit_operation(
            "正在结束二分定位...", self._svc.bisect_reset
        )

    @Slot(result=QObject)
    def bisectLog(self):
        return self._submit_operation("正在读取二分记录...", self._svc.bisect_log)

    # ==================== 暂存 / 取消暂存 ====================
    @Slot(str, result=QObject)
    def stageFile(self, path: str):
        def work() -> tuple[bool, str]:
            ok = self._svc.stage_file(path)
            return ok, f"已暂存 {path}" if ok else f"暂存失败: {path}"

        return self._submit_operation("正在暂存文件...", work)

    @Slot(str, result=QObject)
    def unstageFile(self, path: str):
        def work() -> tuple[bool, str]:
            ok = self._svc.unstage_file(path)
            return ok, f"已取消暂存 {path}" if ok else f"取消暂存失败: {path}"

        return self._submit_operation("正在取消暂存文件...", work)

    @Slot(result=QObject)
    def stageAll(self):
        def work() -> tuple[bool, str]:
            ok = self._svc.stage_all()
            return ok, "已暂存全部改动" if ok else "暂存全部改动失败"

        return self._submit_operation("正在暂存全部改动...", work)

    @Slot(result=QObject)
    def unstageAll(self):
        def work() -> tuple[bool, str]:
            ok = self._svc.unstage_all()
            return ok, "已取消全部暂存" if ok else "取消全部暂存失败"

        return self._submit_operation("正在取消全部暂存...", work)

    @Slot(str, result=QObject)
    def discardFile(self, path: str):
        def work() -> tuple[bool, str]:
            ok = self._svc.discard_file(path)
            return ok, f"已丢弃 {path}" if ok else f"丢弃失败: {path}"

        return self._submit_operation("正在丢弃文件改动...", work)

    # ==================== 差异 ====================
    @Slot(str, bool)
    def requestDiff(self, path: str, staged: bool):
        """后台获取文件差异,完成发 diffReady(repoPath, path, staged, content)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: self._svc.get_diff(path, staged),
            label="获取 diff",
            on_success=lambda data: self.diffReady.emit(
                repo, path, staged, str(data)
            ),
            on_failure=lambda _exc: self.diffReady.emit(repo, path, staged, ""),
        )

    @Slot(str, result="QVariantList")
    def parseDiffFiles(self, raw_diff: str) -> list:
        """解析 diff 文件摘要,供 QML diff viewer 展示和过滤。"""
        return [_diff_file_to_dict(d) for d in GitService.parse_unified_diff(raw_diff)]

    @Slot(str, str, result=str)
    def filterDiffByPath(self, raw_diff: str, path: str) -> str:
        """从多文件 diff 中取指定文件段。"""
        return GitService.filter_unified_diff(raw_diff, path)

    # ==================== 提交 ====================
    @Slot(str, result=QObject)
    def commit(self, message: str):
        return self._submit_operation(
            "正在提交变更...", lambda: self._svc.commit(message)
        )

    @Slot(str, result=QObject)
    def amendCommit(self, message: str):
        return self._submit_operation(
            "正在修补上次提交...", lambda: self._svc.amend_commit(message)
        )

    @Slot(result=QObject)
    def isHeadPushed(self):
        """异步判断最近提交是否已推送到上游。"""
        return self._submit_query(
            self._svc.is_head_pushed,
            label="检查提交推送状态",
        )

    # ==================== 远程同步(异步,经 operationFinished 回传) ====================
    @Slot()
    def push(self):
        self._svc.push()

    @Slot()
    def pushForce(self):
        self._svc.push(force=True)

    @Slot(str, str)
    def pushTo(self, remote: str, branch: str):
        self._svc.push(remote=remote, branch=branch)

    @Slot(str, str)
    def pushForceTo(self, remote: str, branch: str):
        self._svc.push(remote=remote, branch=branch, force=True)

    @Slot()
    def pull(self):
        self._svc.pull()

    @Slot()
    def pullRebase(self):
        self._svc.pull(rebase=True)

    @Slot(str, str)
    def pullFrom(self, remote: str, branch: str):
        self._svc.pull(remote=remote, branch=branch)

    @Slot(str, str)
    def pullRebaseFrom(self, remote: str, branch: str):
        self._svc.pull(remote=remote, branch=branch, rebase=True)

    @Slot()
    def fetch(self):
        self._svc.fetch()

    @Slot()
    def fetchAll(self):
        self._svc.fetch_all()

    @Slot(str)
    def fetchRemote(self, remote: str):
        self._svc.fetch(remote=remote)

    @Slot()
    def forceResetToUpstream(self):
        self._svc.force_reset_to_upstream()

    @Slot(str)
    def quickCommitPush(self, message: str):
        """一键提交推送(异步);结果经 operationStarted/progressUpdated/operationFinished 回传"""
        self._svc.quick_commit_push(
            message,
            callback=lambda ok, msg: self.quickCommitPushFinished.emit(ok, msg),
        )

    @Slot(result=QObject)
    def getRemoteInfo(self):
        """异步读取远程列表，返回 PrismQML ``TaskHandle``。"""
        return self._submit_query(
            lambda: [
                {"name": name, "url": url}
                for name, url in self._svc.get_remote_info()
            ],
            label="获取远程列表",
        )

    # ==================== 提交历史 ====================
    def getLog(self, count: int, skip: int, fast_mode: bool) -> list:
        """提交历史(分页) -> [{hash, shortHash, author, ...}, ...]"""
        return [_commit_to_dict(c) for c in self._svc.get_log(count, skip, fast_mode)]

    @Slot(int, int, bool)
    def requestLog(self, count: int, skip: int, include_all_refs: bool = False):
        """后台分页获取提交,完成发 logReady(repoPath, skip, list),不阻塞主线程。"""
        repo = self._svc.repo_path or ""
        self._log_request_serial += 1
        request_serial = self._log_request_serial

        def work():
            return [
                    _commit_to_dict(c)
                    for c in self._svc.get_graph_log_at(
                        repo, count, skip, include_all_refs
                    )
                ]

        def completed(batch: list) -> None:
            if request_serial != self._log_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            self.logReady.emit(repo, skip, batch)

        return self._submit_query(
            work,
            label="获取提交历史",
            on_success=completed,
            on_failure=lambda _exc: completed([]),
        )

    @Slot(str, str, bool)
    def requestSearch(
        self, query: str, search_type: str, include_all_refs: bool = False
    ):
        """后台搜索提交,完成发 searchReady(repoPath, list)。"""
        repo = self._svc.repo_path or ""
        self._search_request_serial += 1
        request_serial = self._search_request_serial

        def work():
            return [
                    _commit_to_dict(c)
                    for c in self._svc.search_commits_at(
                        repo, query, search_type, 100, include_all_refs
                    )
                ]

        def completed(results: list) -> None:
            if request_serial != self._search_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            self.searchReady.emit(repo, results)

        return self._submit_query(
            work,
            label="搜索提交",
            on_success=completed,
            on_failure=lambda _exc: completed([]),
        )

    def isLargeRepo(self) -> bool:
        return self._svc.is_large_repo()

    def searchCommits(self, query: str, search_type: str, count: int) -> list:
        return [_commit_to_dict(c) for c in self._svc.search_commits(query, search_type, count)]

    def getCommitCountAfter(self, commit_hash: str) -> int:
        return self._svc.get_commit_count_after(commit_hash)

    @Slot(str, result=QObject)
    def checkoutCommit(self, commit_hash: str):
        return self._submit_operation(
            "正在检出提交...", lambda: self._svc.checkout_branch(commit_hash)
        )

    @Slot(str, result=QObject)
    def revertCommit(self, commit_hash: str):
        return self._submit_operation(
            "正在撤销提交...", lambda: self._svc.revert_commit(commit_hash)
        )

    @Slot(str, str, result=QObject)
    def resetToCommit(self, commit_hash: str, mode: str):
        return self._submit_operation(
            "正在回滚到指定提交...",
            lambda: self._svc.reset_to_commit(commit_hash, mode),
        )

    @Slot(str, result=QObject)
    def cherryPick(self, commit_hash: str):
        return self._submit_operation(
            "正在 Cherry-pick 提交...",
            lambda: self._svc.cherry_pick(commit_hash),
        )

    @Slot(str, str, result=QObject)
    def cherryPickToBranch(self, commit_hash: str, target_branch: str):
        return self._submit_operation(
            f"正在将提交应用到 {target_branch}...",
            lambda: self._svc.cherry_pick_to_branch(commit_hash, target_branch),
        )

    # ==================== 分支 ====================
    @Slot()
    def requestBranches(self):
        """后台获取分支列表,完成发 branchesReady(repoPath,list)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: [_branch_to_dict(b) for b in self._svc.get_branches()],
            label="获取分支列表",
            on_success=lambda data: self.branchesReady.emit(repo, data),
            on_failure=lambda _exc: self.branchesReady.emit(repo, []),
        )

    @Slot(str, bool, result=QObject)
    def createBranch(self, branch: str, checkout: bool):
        return self._submit_operation(
            "正在创建分支...",
            lambda: self._svc.create_branch(branch, checkout),
        )

    @Slot(str, str, bool, result=QObject)
    def createBranchAt(
        self, branch: str, start_point: str, checkout: bool
    ):
        return self._submit_operation(
            "正在创建分支...",
            lambda: self._svc.create_branch(
                branch, checkout=checkout, start_point=start_point
            ),
            publish=False,
        )

    @Slot(str, result=QObject)
    def checkoutBranch(self, branch: str):
        return self._submit_operation(
            f"正在切换到分支 {branch}...",
            lambda: self._svc.checkout_branch(branch),
        )

    @Slot(str, str, result=QObject)
    def checkoutRemoteBranch(self, remote_branch: str, local_branch: str):
        return self._submit_operation(
            "正在检出远程分支...",
            lambda: self._svc.checkout_remote_branch(
                remote_branch, local_branch
            ),
        )

    @Slot(str, bool, result=QObject)
    def deleteBranch(self, branch: str, force: bool):
        return self._submit_operation(
            f"正在删除分支 {branch}...",
            lambda: self._svc.delete_branch(branch, force),
        )

    @Slot(str)
    def deleteRemoteBranch(self, remote_branch: str):
        """后台删除远程分支；本地分支不会被删除。"""
        return self._submit_operation(
            f"正在删除远程分支 {remote_branch}...",
            lambda: self._svc.delete_remote_branch(remote_branch),
        )

    @Slot(str, str, result=QObject)
    def renameBranch(self, old_name: str, new_name: str):
        return self._submit_operation(
            "正在重命名分支...",
            lambda: self._svc.rename_branch(old_name, new_name),
        )

    @Slot(str, str, str, result=QObject)
    def setUpstream(self, local_branch: str, remote: str, remote_branch: str):
        return self._submit_operation(
            "正在设置上游分支...",
            lambda: self._svc.set_upstream(local_branch, remote, remote_branch),
        )

    @Slot(str)
    def mergeBranch(self, branch: str):
        """合并分支(异步);结果经 operationFinished 回传"""
        self._svc.merge_branch(branch)

    @Slot(str, result=QObject)
    def rebaseOnto(self, branch: str):
        return self._submit_operation(
            f"正在 Rebase 到 {branch}...",
            lambda: self._svc.rebase_onto(branch),
        )

    @Slot(result=QObject)
    def pruneRemote(self):
        return self._submit_operation(
            "正在清理远程分支引用...", self._svc.prune_remote
        )

    # ==================== 冲突 ====================
    def isMerging(self) -> bool:
        return self._svc.is_merging()

    def getConflictOperation(self) -> str:
        return self._svc.get_operation_state()

    @Slot()
    def requestConflicts(self):
        """后台获取冲突文件,完成发 conflictsReady(repoPath,list)。"""
        repo = self._svc.repo_path or ""
        def completed(result: object) -> None:
            operation, data = result
            self.conflictStateReady.emit(repo, operation)
            self.conflictsReady.emit(repo, data)

        return self._submit_query(
            lambda: (
                self._svc.get_operation_state(),
                [_conflict_to_dict(c) for c in self._svc.get_conflicts()],
            ),
            label="获取冲突状态",
            on_success=completed,
            on_failure=lambda _exc: completed(("", [])),
        )

    @Slot(str, result=QObject)
    def resolveWithOurs(self, path: str):
        return self._submit_operation(
            "正在使用当前分支版本解决冲突...",
            lambda: self._svc.resolve_conflict_with_ours(path),
        )

    @Slot(str, result=QObject)
    def resolveWithTheirs(self, path: str):
        return self._submit_operation(
            "正在使用对方分支版本解决冲突...",
            lambda: self._svc.resolve_conflict_with_theirs(path),
        )

    @Slot(result=QObject)
    def abortMerge(self):
        return self._submit_operation("正在中止合并...", self._svc.abort_merge)

    @Slot(result=QObject)
    def continueRebase(self):
        return self._submit_operation("正在继续 Rebase...", self._svc.continue_rebase)

    @Slot(result=QObject)
    def abortRebase(self):
        return self._submit_operation("正在中止 Rebase...", self._svc.abort_rebase)

    @Slot(result=QObject)
    def skipRebase(self):
        return self._submit_operation("正在跳过 Rebase 提交...", self._svc.skip_rebase)

    @Slot(result=QObject)
    def continueCherryPick(self):
        return self._submit_operation(
            "正在继续 Cherry-pick...", self._svc.continue_cherry_pick
        )

    @Slot(result=QObject)
    def abortCherryPick(self):
        return self._submit_operation(
            "正在中止 Cherry-pick...", self._svc.abort_cherry_pick
        )

    @Slot(result=QObject)
    def continueRevert(self):
        return self._submit_operation("正在继续 Revert...", self._svc.continue_revert)

    @Slot(result=QObject)
    def abortRevert(self):
        return self._submit_operation("正在中止 Revert...", self._svc.abort_revert)

    # ==================== Stash ====================
    @Slot()
    def requestStashList(self):
        """后台获取 stash 列表,完成发 stashListReady(repoPath,list)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: [
                {"id": sid, "message": msg}
                for sid, msg in self._svc.stash_list()
            ],
            label="获取 Stash 列表",
            on_success=lambda data: self.stashListReady.emit(repo, data),
            on_failure=lambda _exc: self.stashListReady.emit(repo, []),
        )

    @Slot(str, bool, bool, result=QObject)
    def stashSave(self, message: str, include_untracked: bool, keep_index: bool):
        return self._submit_operation(
            "正在保存 Stash...",
            lambda: self._svc.stash_save(
                message, include_untracked, keep_index
            ),
        )

    @Slot(str, result=QObject)
    def stashPop(self, stash_id: str):
        return self._submit_operation(
            "正在恢复并删除 Stash...", lambda: self._svc.stash_pop(stash_id)
        )

    @Slot(str, result=QObject)
    def stashApply(self, stash_id: str):
        return self._submit_operation(
            "正在应用 Stash...", lambda: self._svc.stash_apply(stash_id)
        )

    @Slot(str, result=QObject)
    def stashDrop(self, stash_id: str):
        return self._submit_operation(
            "正在删除 Stash...", lambda: self._svc.stash_drop(stash_id)
        )

    @Slot(result=QObject)
    def stashClear(self):
        return self._submit_operation("正在清空 Stash...", self._svc.stash_clear)

    @Slot(str, result=QObject)
    def stashShow(self, stash_id: str):
        return self._submit_query(
            lambda: self._svc.stash_show(stash_id),
            label="查看 Stash",
        )

    @Slot(str, str, result=QObject)
    def stashBranch(self, branch: str, stash_id: str):
        return self._submit_operation(
            "正在从 Stash 创建分支...",
            lambda: self._svc.stash_branch(branch, stash_id),
        )

    # ==================== Tag ====================
    @Slot()
    def requestTags(self):
        """后台获取标签列表,完成发 tagsReady(repoPath,list)。"""
        repo = self._svc.repo_path or ""
        self._tags_request_serial += 1
        request_serial = self._tags_request_serial

        def work():
            return [
                    {"name": n, "hash": h, "message": m}
                    for n, h, m in self._svc.get_tags_at(repo)
                ]

        def completed(data: list) -> None:
            if request_serial != self._tags_request_serial:
                return
            self.tagsReady.emit(repo, data)

        return self._submit_query(
            work,
            label="获取标签列表",
            on_success=completed,
            on_failure=lambda _exc: completed([]),
        )

    @Slot(str, str, bool, result=QObject)
    def createTag(self, name: str, message: str, annotated: bool):
        return self._submit_operation(
            "正在创建标签...",
            lambda: self._svc.create_tag(name, message, annotated=annotated),
        )

    @Slot(str, result=QObject)
    def deleteTag(self, name: str):
        return self._submit_operation(
            f"正在删除标签 {name}...", lambda: self._svc.delete_tag(name)
        )

    @Slot(str)
    def pushTag(self, name: str):
        """后台推送标签到远程(网络操作);结果经 operationStarted/Finished 回传。"""
        self.progressUpdated.emit(0, "正在准备推送标签")
        return self._submit_operation(
            f"正在推送标签 {name}...", lambda: self._svc.push_tag(name)
        )

    @Slot()
    def pushAllTags(self):
        """后台推送所有标签(网络操作);结果经 operationStarted/Finished 回传。"""
        self.progressUpdated.emit(0, "正在准备推送标签")
        return self._submit_operation(
            "正在推送所有标签...", self._svc.push_all_tags
        )

    @Slot(str, str)
    def deleteRemoteTag(self, name: str, remote: str):
        """后台删除远程标签(网络操作);本地 tag 不会被删除。"""
        return self._submit_operation(
            f"正在删除远程标签 {remote}/{name}...",
            lambda: self._svc.delete_remote_tag(name, remote),
        )

    @Slot(str, result=QObject)
    def checkoutTag(self, name: str):
        return self._submit_operation(
            f"正在检出标签 {name}...", lambda: self._svc.checkout_tag(name)
        )

    # ==================== 初始化 / 克隆 ====================
    @Slot(str, result=QObject)
    def initRepo(self, path: str):
        return self._submit_operation(
            "正在初始化 Git 仓库...", lambda: self._svc.init(path)
        )

    @Slot(str, str)
    def clone(self, url: str, path: str):
        """克隆(异步);结果经 operationFinished 回传"""
        self._svc.clone(url, path)

    # ==================== 用户信息 / 远程 ====================
    @Slot(result=QObject)
    def getUserInfo(self):
        """当前仓库生效的用户配置 -> [name, email]"""
        return self._submit_query(
            lambda: list(self._svc.get_user_info()),
            label="获取仓库用户信息",
        )

    @Slot(result=QObject)
    def getGlobalUserInfo(self):
        """全局用户配置 -> [name, email]"""
        return self._submit_query(
            lambda: list(self._svc.get_user_info(True)),
            label="获取全局 Git 用户信息",
        )

    @Slot(str, str, bool, result=QObject)
    def setUserInfo(self, name: str, email: str, global_scope: bool):
        return self._submit_operation(
            "正在保存 Git 用户信息...",
            lambda: self._svc.set_user_info(name, email, global_scope),
        )

    @Slot(str, str, result=QObject)
    def addRemote(self, name: str, url: str):
        return self._submit_operation(
            "正在添加远程仓库...", lambda: self._svc.add_remote(name, url)
        )

    @Slot(str, result=QObject)
    def removeRemote(self, name: str):
        return self._submit_operation(
            "正在删除远程仓库...", lambda: self._svc.remove_remote(name)
        )

    @Slot(str, str, result=QObject)
    def setRemoteUrl(self, name: str, url: str):
        return self._submit_operation(
            "正在更新远程仓库地址...",
            lambda: self._svc.set_remote_url(name, url),
        )

    @Slot(str, str, result=QObject)
    def renameRemote(self, old_name: str, new_name: str):
        return self._submit_operation(
            "正在重命名远程仓库...",
            lambda: self._svc.rename_remote(old_name, new_name),
        )

    def getRemoteUrl(self, name: str) -> str:
        return self._svc.get_remote_url(name)

    # ==================== 文件历史 ====================
    @Slot(str, int)
    def requestFileHistory(self, path: str, count: int):
        """后台获取文件历史,完成发 fileHistoryReady(repoPath, path, list)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: [
                _commit_to_dict(c)
                for c in self._svc.get_file_history(path, count)
            ],
            label="获取文件历史",
            on_success=lambda data: self.fileHistoryReady.emit(repo, path, data),
            on_failure=lambda _exc: self.fileHistoryReady.emit(repo, path, []),
        )

    @Slot(str, str)
    def requestFileContentAtCommit(self, path: str, commit_hash: str):
        """后台获取文件在某提交的内容,完成发 fileContentReady(repoPath, path, hash, content)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: self._svc.get_file_content_at_commit(path, commit_hash),
            label="获取提交中的文件内容",
            on_success=lambda data: self.fileContentReady.emit(
                repo, path, commit_hash, str(data)
            ),
            on_failure=lambda _exc: self.fileContentReady.emit(
                repo, path, commit_hash, ""
            ),
        )

    @Slot(str, str, str)
    def requestDiffBetween(self, path: str, c1: str, c2: str):
        """后台对比文件两提交差异,完成发 diffBetweenReady(repoPath, path, c1, c2, diff)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: self._svc.diff_file_between_commits(path, c1, c2),
            label="对比文件提交差异",
            on_success=lambda data: self.diffBetweenReady.emit(
                repo, path, c1, c2, str(data)
            ),
            on_failure=lambda _exc: self.diffBetweenReady.emit(
                repo, path, c1, c2, ""
            ),
        )

    # ==================== 提交详情 ====================
    @Slot(str, result=QObject)
    def getCommitDetail(self, commit_hash: str):
        return self._submit_query(
            lambda: (
                _commit_to_dict(c)
                if (c := self._svc.get_commit_detail(commit_hash))
                else {}
            ),
            label="获取提交详情",
        )

    @Slot(str)
    def requestCommitFiles(self, commit_hash: str):
        """后台获取提交变更文件,完成发 commitFilesReady(repoPath, hash, list)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: [
                _file_change_to_dict(fc)
                for fc in self._svc.get_commit_files(commit_hash)
            ],
            label="获取提交文件",
            on_success=lambda data: self.commitFilesReady.emit(
                repo, commit_hash, data
            ),
            on_failure=lambda _exc: self.commitFilesReady.emit(
                repo, commit_hash, []
            ),
        )

    @Slot(str)
    def requestCommitDiff(self, commit_hash: str):
        """后台获取提交 diff,完成发 commitDiffReady(repoPath, hash, diff)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: self._svc.get_commit_diff(commit_hash),
            label="获取提交 diff",
            on_success=lambda data: self.commitDiffReady.emit(
                repo, commit_hash, str(data)
            ),
            on_failure=lambda _exc: self.commitDiffReady.emit(
                repo, commit_hash, ""
            ),
        )

    # ==================== Reflog ====================
    @Slot(int)
    def requestReflog(self, count: int):
        """后台获取 reflog,完成发 reflogReady(repoPath,list)。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: [
                {"hash": h, "ref": r, "message": m}
                for h, r, m in self._svc.get_reflog(count)
            ],
            label="获取 Reflog",
            on_success=lambda data: self.reflogReady.emit(repo, data),
            on_failure=lambda _exc: self.reflogReady.emit(repo, []),
        )

    # ==================== 冲突文件内容 ====================
    @Slot(str, result=str)
    def readConflictFile(self, path: str) -> str:
        """读取工作区冲突文件原始内容(带冲突标记);路径越界保护。"""
        import os
        repo = self._svc.repo_path
        if not repo:
            return ""
        full_path = os.path.join(repo, path)
        real_path = os.path.realpath(full_path)
        repo_real = os.path.realpath(repo)
        if not real_path.startswith(repo_real + os.sep):
            logger.warning(f"拒绝读取仓库外路径: {path}")
            return ""
        try:
            with open(real_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except OSError as e:
            logger.warning(f"读取冲突文件失败 {path}: {e}")
            return ""

    def _repo_rule_file_path(self, name: str) -> tuple[Path | None, str]:
        """解析仓库根目录规则文件，并拒绝越界/未知文件名。"""
        repo = self._svc.repo_path
        if not repo:
            return None, "当前没有打开仓库"
        if name not in self._REPO_RULE_FILES:
            return None, "只允许编辑 .gitignore 和 .gitattributes"

        repo_real = Path(os.path.realpath(repo))
        target = Path(os.path.realpath(os.path.join(repo_real, name)))
        try:
            if os.path.commonpath((str(repo_real), str(target))) != str(repo_real):
                return None, "规则文件必须位于仓库根目录"
        except ValueError:
            return None, "规则文件路径无效"
        return target, ""

    @Slot(str, result=str)
    def readRepoRuleFile(self, name: str) -> str:
        """读取仓库根目录的 .gitignore/.gitattributes，不存在时返回空文本。"""
        path, error = self._repo_rule_file_path(name)
        if path is None:
            if error != "当前没有打开仓库":
                logger.warning(f"读取规则文件被拒绝 {name}: {error}")
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""
        except OSError as e:
            logger.warning(f"读取规则文件失败 {name}: {e}")
            return ""

    @Slot(str, str, result="QVariantList")
    def saveRepoRuleFile(self, name: str, content: str) -> list:
        """原子保存仓库根目录的 .gitignore/.gitattributes。"""
        path, error = self._repo_rule_file_path(name)
        if path is None:
            logger.warning(f"保存规则文件被拒绝 {name}: {error}")
            return [False, error]

        temp_name = ""
        try:
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{name.lstrip('.')}.", suffix=".tmp", dir=str(path.parent)
            )
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
            os.replace(temp_name, path)
            temp_name = ""
        except OSError as e:
            logger.warning(f"保存规则文件失败 {name}: {e}")
            return [False, f"保存 {name} 失败: {e}"]
        finally:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError as e:
                    logger.warning(f"清理规则文件临时文件失败 {temp_name}: {e}")

        # 规则文件属于工作区变更，立即通知状态页，并让轮询从新基线开始。
        self._reset_poll_baseline()
        self.statusChanged.emit()
        return [True, f"已保存 {name}"]
