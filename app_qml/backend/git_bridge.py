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
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional

from PySide6.QtCore import QObject, Slot, Signal, Property
from prismqml import current_task

from app.common.git_service import (
    GitService, FileChange, CommitInfo, BranchInfo, ConflictInfo,
    WorktreeInfo, SubmoduleInfo, DiffFile,
    MAX_CLEAN_PREVIEW, MAX_CONFLICT_FILE_SIZE, MAX_RULE_FILE_SIZE,
)
from app.common.logger import get_logger
from app.common.prism_task import submit_to_pool
from app_qml.backend.file_change_model import FileChangeListModel

logger = get_logger("GitBridge")


def _timeline_trace_enabled() -> bool:
    """Return whether the opt-in timeline trace is enabled."""
    return os.environ.get("GITORA_TIMELINE_TRACE", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


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
        "locked": w.locked,
        "lockedReason": w.locked_reason,
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
    operationBusyChanged = Signal()
    repoPathChanged = Signal(str)
    repoOpened = Signal(bool, str)   # 异步打开完成(成功, 路径/错误消息)
    repoOpenRejected = Signal(str, str)  # (请求路径, 拒绝原因)
    # 启动恢复上次会话的标签页(全部已打开仓库, 活动仓库)
    openedReposRestored = Signal("QVariantList", str)
    statusReady = Signal(str, int)              # 后台状态就绪(repoPath, 变更数量)
    branchReady = Signal(str, str)             # 后台当前分支就绪(repoPath, 分支)
    historyCountReady = Signal(str, int, bool)  # (repoPath, 总提交数, 是否全部引用)
    logReady = Signal(str, int, "QVariantList")    # 后台提交分页就绪(repoPath, skip, 批次)
    searchPreviewReady = Signal(str, "QVariantList")  # 搜索阶段结果(repoPath, 结果)
    searchReady = Signal(str, "QVariantList")       # 后台搜索结果就绪(repoPath, 结果)
    # 以下为耗时操作异步化新增信号(均带请求参数供前端校验防过期)
    diffReady = Signal(str, str, bool, str)              # (repoPath, path, staged, diff内容)
    commitDiffReady = Signal(str, str, str)              # (repoPath, hash, diff)
    commitFileDiffReady = Signal(str, str, str, str)     # (repoPath, hash, path, diff)
    branchesReady = Signal(str, "QVariantList")          # (repoPath, 分支列表)
    tagsReady = Signal(str, "QVariantList")              # (repoPath, 标签列表)
    fileHistoryReady = Signal(str, str, "QVariantList")  # (repoPath, path, 提交列表)
    conflictsReady = Signal(str, "QVariantList")         # (repoPath, 冲突文件列表)
    conflictStateReady = Signal(str, str)                 # (repoPath, 操作类型)
    conflictFileReady = Signal(str, str, "QVariantList", bool)  # (repoPath, path, lines, truncated)
    commitFilesReady = Signal(str, str, "QVariantList", int, bool, "QVariantMap")  # (repoPath, hash, 预览, 总数, 是否截断, 状态统计)
    fileContentReady = Signal(str, str, str, str)        # (repoPath, path, hash, 内容)
    diffBetweenReady = Signal(str, str, str, str, str)   # (repoPath, path, c1, c2, diff)
    stashListReady = Signal(str, "QVariantList")         # (repoPath, stash 列表)
    cleanPreviewReady = Signal(str, "QVariantList", int, bool)  # (repoPath, 预览, 总数, 是否截断)
    repoRuleFileReady = Signal(str, str, str)             # (repoPath, name, content)
    reflogReady = Signal(str, "QVariantList")            # (repoPath, reflog 列表)
    advancedStateReady = Signal(str, "QVariantList", "QVariantList")  # (repoPath, worktree, submodule)
    # 外部变化轮询间隔(ms):覆盖命令行/其他 Git 工具引起的状态变化
    _POLL_INTERVAL_MS = 2000

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._svc = GitService(self)
        self._file_change_model = FileChangeListModel(self)
        self._active_operation_count = 0
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
        self._svc.operationStarted.connect(self._forward_service_operation_started)
        self._svc.operationFinished.connect(self._forward_service_operation_finished)
        self._svc.progressUpdated.connect(self.progressUpdated)
        self._log_request_serial = 0
        self._search_request_serial = 0
        self._search_task = None
        self._current_branch_request_serial = 0
        self._history_count_request_serial = 0
        self._branches_request_serial = 0
        self._tags_request_serial = 0
        self._advanced_request_serial = 0
        self._open_request_serial = 0
        self._timeline_trace_sequence = 0
        # 已打开仓库快照的写盘序号(主线程分配,用于丢弃线程池乱序的旧快照)
        self._opened_repos_save_sequence = 0

        # 指纹计算放后台线程(跑 git 命令,不能阻塞主线程);
        # 用 _poll_busy 防重入,避免上一轮未完又起一轮。
        # QTimer 在主线程排队;emit 信号跨线程安全(排队回主线程)
        from PySide6.QtCore import QTimer
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_tick)
        self._poll_timer.start()

    def _timeline_trace(self, event: str, **fields: object) -> None:
        """Write one opt-in backend event with a process-local sequence."""
        if not _timeline_trace_enabled():
            return
        self._timeline_trace_sequence += 1
        suffix = " ".join(
            f"{key}={value!r}" for key, value in fields.items()
        )
        logger.debug(
            "[TIMELINE_TRACE] side=python seq=%d t=%d %s%s",
            self._timeline_trace_sequence,
            time.time_ns() // 1_000_000,
            event,
            f" {suffix}" if suffix else "",
        )

    def _submit_query(
        self,
        function: Callable[[], Any],
        *,
        label: str,
        on_success: Callable[[Any], None] | None = None,
        on_failure: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[Any], None] | None = None,
        on_cancelled: Callable[[], None] | None = None,
        on_finished: Callable[[], None] | None = None,
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
            on_progress=on_progress,
            on_cancelled=on_cancelled,
            on_finished=on_finished,
        )

    def _submit_operation(
        self,
        description: str,
        function: Callable[[], tuple[bool, str]],
        *,
        publish: bool = True,
    ):
        """提交一个返回 ``(成功, 消息)`` 的 Git 操作。"""
        self._begin_operation()
        if publish:
            self.operationStarted.emit(description)

        def succeeded(result: object) -> None:
            try:
                ok, message = result
            except (TypeError, ValueError):
                logger.error(f"Git 后台操作返回值无效: {result!r}")
                self._finish_operation()
                if publish:
                    self.operationFinished.emit(False, "Git 操作返回值无效")
                return
            self._finish_operation()
            if publish:
                self.operationFinished.emit(bool(ok), str(message))

        def failed(exc: BaseException) -> None:
            logger.warning(
                f"Git 后台操作异常: {type(exc).__name__}: {exc}"
            )
            self._finish_operation()
            if publish:
                self.operationFinished.emit(
                    False,
                    "Git 操作发生异常，请重试；技术详情已记录到日志。",
                )

        def cancelled() -> None:
            self._finish_operation()
            if publish:
                self.operationFinished.emit(False, "Git 操作已取消")

        return submit_to_pool(
            function,
            on_success=succeeded,
            on_failure=failed,
            on_cancelled=cancelled,
        )

    def _begin_operation(self) -> None:
        was_busy = self._active_operation_count > 0
        self._active_operation_count += 1
        if not was_busy:
            self.operationBusyChanged.emit()

    def _finish_operation(self) -> None:
        was_busy = self._active_operation_count > 0
        self._active_operation_count = max(0, self._active_operation_count - 1)
        if was_busy and self._active_operation_count == 0:
            self.operationBusyChanged.emit()

    @Slot(str)
    def _forward_service_operation_started(self, message: str) -> None:
        self._begin_operation()
        self.operationStarted.emit(message)

    @Slot(bool, str)
    def _forward_service_operation_finished(self, ok: bool, message: str) -> None:
        self._finish_operation()
        self.operationFinished.emit(ok, message)

    def _reset_poll_baseline(self, reason: str = "unspecified"):
        """使当前基线失效；下一轮只建新基线，不重复发刷新。"""
        self._poll_generation += 1
        self._poll_fingerprint = ""
        self._poll_repo = self._svc.repo_path or ""
        self._timeline_trace(
            "poll.baseline_reset",
            reason=reason,
            generation=self._poll_generation,
            repo=self._poll_repo,
        )

    @Slot()
    def _forward_service_status_changed(self):
        """转发内部变更一次，并阻止轮询把同一变化再转发一次。"""
        self._timeline_trace(
            "statusChanged.emit",
            source="GitService.statusChanged",
            repo=self._svc.repo_path or "",
        )
        self._reset_poll_baseline("service_status_changed")
        self.statusChanged.emit()

    def _poll_tick(self):
        """定时器回调(主线程):把指纹计算交给 PrismQML 线程池。"""
        repo = self._svc.repo_path or ""
        if not repo or self._poll_busy:
            return
        self._poll_busy = True
        self._poll_repo = repo
        generation = self._poll_generation
        self._timeline_trace(
            "poll.fingerprint_request",
            repo=repo,
            generation=generation,
        )
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
        self._timeline_trace(
            "poll.fingerprint_ready",
            repo=repo,
            generation=generation,
            current_generation=self._poll_generation,
            fingerprint=fp[:12] if fp else "",
        )
        # 仓库已切走或内部操作已使基线换代 → 丢弃过期结果。
        if (
            generation != self._poll_generation
            or repo != (self._svc.repo_path or "")
        ):
            self._timeline_trace(
                "poll.fingerprint_drop",
                reason="stale_generation_or_repo",
            )
            self._poll_busy = False
            return
        if fp == "":
            # 读取失败/仓库无效:不更新基线也不触发,等下一轮
            self._timeline_trace("poll.fingerprint_drop", reason="empty")
            self._poll_busy = False
            return
        if self._poll_fingerprint == "":
            # 首次:仅建立基线,不触发(打开仓库已各视图各自 reload 过)
            self._poll_fingerprint = fp
            self._timeline_trace(
                "poll.baseline_established",
                fingerprint=fp[:12],
            )
        elif fp != self._poll_fingerprint:
            previous = self._poll_fingerprint
            self._poll_fingerprint = fp
            self._timeline_trace(
                "statusChanged.emit",
                source="fingerprint_changed",
                previous_fingerprint=previous[:12],
                fingerprint=fp[:12],
                repo=repo,
            )
            self.statusChanged.emit()
        else:
            self._timeline_trace(
                "poll.fingerprint_unchanged",
                fingerprint=fp[:12],
            )
        self._poll_busy = False

    # ==================== 属性 ====================
    @Property(str, notify=repoPathChanged)
    def repoPath(self) -> str:
        return self._svc.repo_path or ""

    @Property(bool, notify=operationBusyChanged)
    def operationBusy(self) -> bool:
        return self._active_operation_count > 0

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
            self._reset_poll_baseline("set_repo_path")
            self.repoPathChanged.emit(self._svc.repo_path or "")
        return ok

    @Slot(str)
    def openRepoAsync(self, path: str):
        """后台打开仓库,不阻塞主线程;成功时由 repoPathChanged 驱动各视图刷新。"""
        current_path = self._svc.repo_path or ""
        same_repo = os.path.normcase(os.path.normpath(path)) == os.path.normcase(
            os.path.normpath(current_path)
        )
        if self.operationBusy and not same_repo:
            message = "Git 操作正在进行，请等待完成后再切换仓库"
            self.repoOpened.emit(False, path)
            self.repoOpenRejected.emit(path, message)
            return None

        self._open_request_serial += 1
        request_serial = self._open_request_serial

        def completed(ok: object) -> None:
            if request_serial != self._open_request_serial:
                return
            if ok:
                self._svc.activate_repo_path(path, emit_status=False)
                from app.common.recent_repos import recentReposManager
                recentReposManager.add(self._svc.repo_path or path)
                self._reset_poll_baseline("open_repo")
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

    @Slot()
    def restoreLastRepoAsync(self):
        """启动时异步恢复上次关闭时仍然打开的全部仓库标签页。

        标签栏先按快照重建全部标签，再只真正打开活动仓库；其余标签保持
        未读取状态，等用户点选时才走 openRepoAsync，避免启动时批量跑 Git。
        """
        if self._svc.repo_path:
            return

        def read_snapshot() -> tuple[list, str]:
            """后台读快照：每个路径一次 exists()，不能放主线程。"""
            from app.common.opened_repos import openedReposManager
            opened_repos, active_repo = openedReposManager.get_snapshot()
            if not opened_repos:
                # 旧版本升级上来没有会话快照，退回最近一次打开的仓库。
                from app.common.recent_repos import recentReposManager
                opened_repos = recentReposManager.get_all()[:1]
                active_repo = opened_repos[0] if opened_repos else ""
            if not active_repo and opened_repos:
                active_repo = opened_repos[0]
            return opened_repos, active_repo

        def apply_snapshot(result: object) -> None:
            try:
                opened_repos, active_repo = result
            except (TypeError, ValueError):
                logger.error(f"已打开仓库快照返回值无效: {result!r}")
                self.openedReposRestored.emit([], "")
                return
            # 即使快照为空也要发信号：标签栏据此结束“恢复中”状态，之后才允许回写。
            self.openedReposRestored.emit(opened_repos, active_repo)
            if active_repo:
                self.openRepoAsync(active_repo)

        return self._submit_query(
            read_snapshot,
            label="读取已打开仓库快照",
            on_success=apply_snapshot,
            # 读失败也要放行前端，否则标签栏永远停在“恢复中”，之后都不回写。
            on_failure=lambda _exc: self.openedReposRestored.emit([], ""),
        )

    @Slot(result="QVariantList")
    def getOpenedRepos(self) -> list:
        """上次会话仍然打开的仓库 -> [path, ...]（含磁盘检查，勿在主线程调）"""
        from app.common.opened_repos import openedReposManager
        return openedReposManager.get_all()

    @Slot(result=str)
    def getActiveOpenedRepo(self) -> str:
        """上次会话的活动仓库路径（含磁盘检查，勿在主线程调）"""
        from app.common.opened_repos import openedReposManager
        return openedReposManager.get_active()

    @Slot("QVariantList", str)
    def saveOpenedRepos(self, paths: list, active: str):
        """保存当前打开的标签页快照；写盘放后台线程，不阻塞主线程。

        序号在主线程按调用顺序分配，随快照带到后台；线程池不保证完成顺序，
        靠它丢弃迟到的旧快照，避免旧状态覆盖新状态。
        """
        snapshot = [str(path) for path in (paths or []) if str(path or "")]
        active_path = str(active or "")
        self._opened_repos_save_sequence += 1
        sequence = self._opened_repos_save_sequence

        def persist() -> None:
            from app.common.opened_repos import openedReposManager
            openedReposManager.replace(snapshot, active_path, sequence=sequence)

        return self._submit_query(persist, label="保存已打开仓库")

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

    @Slot()
    def requestCurrentBranch(self):
        """异步读取当前分支，经强类型 ``branchReady`` 信号返回给 QML。"""
        repo = self._svc.repo_path or ""
        self._current_branch_request_serial += 1
        request_serial = self._current_branch_request_serial

        def completed(branch: str) -> None:
            if request_serial != self._current_branch_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            self.branchReady.emit(repo, branch)

        return self._submit_query(
            lambda: self._svc.get_current_branch_at(repo),
            label="获取当前分支",
            on_success=lambda branch: completed(str(branch)),
            on_failure=lambda _exc: completed(""),
        )

    # ==================== 仓库维护 ====================
    @Slot()
    def requestCleanPreview(self):
        """后台获取有界清理预览。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            self._svc.clean_preview_limited,
            label="预览待清理文件",
            on_success=lambda data: self.cleanPreviewReady.emit(
                repo, data[0], data[1], data[2]
            ),
            on_failure=lambda _exc: self.cleanPreviewReady.emit(
                repo, [], 0, False
            ),
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
        repo_path = self._svc.repo_path or ""
        return self._submit_operation(
            "正在移除工作树...",
            lambda: self._svc.remove_worktree_at(repo_path, path, force),
        )

    @Slot(result=QObject)
    def pruneWorktrees(self):
        return self._submit_operation(
            "正在清理失效工作树...", self._svc.prune_worktrees
        )

    @Slot(result=QObject)
    def previewDetachedWorktreeCleanup(self):
        repo_path = self._svc.repo_path or ""

        def query():
            ok, removable, skipped, message = (
                self._svc.preview_detached_worktree_cleanup_at(repo_path)
            )
            return {
                "ok": ok,
                "message": message,
                "repoPath": repo_path,
                "removable": removable,
                "skipped": [
                    {"path": path, "reason": reason}
                    for path, reason in skipped
                ],
            }

        return self._submit_query(query, label="预览游离工作树清理")

    @Slot("QVariantList", result=QObject)
    def removeDetachedWorktrees(self, paths: list):
        repo_path = self._svc.repo_path or ""
        requested_paths = [str(path) for path in (paths or [])]
        return self._submit_operation(
            "正在清理游离工作树...",
            lambda: self._svc.remove_detached_worktrees_at(
                repo_path, requested_paths
            ),
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
    @Slot(bool, result=QObject)
    def requestHistoryCount(self, include_all_refs: bool = False):
        """后台统计当前历史范围的完整提交数,经强类型信号回传。"""
        repo = self._svc.repo_path or ""
        self._history_count_request_serial += 1
        request_serial = self._history_count_request_serial
        scope = bool(include_all_refs)

        def completed(count: int) -> None:
            if request_serial != self._history_count_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            self.historyCountReady.emit(repo, int(count), scope)

        return self._submit_query(
            lambda: self._svc.get_commit_count_at(repo, scope),
            label="获取提交总数",
            on_success=completed,
            on_failure=lambda _exc: completed(-1),
        )

    def getLog(self, count: int, skip: int, fast_mode: bool) -> list:
        """提交历史(分页) -> [{hash, shortHash, author, ...}, ...]"""
        return [_commit_to_dict(c) for c in self._svc.get_log(count, skip, fast_mode)]

    @Slot(int, int, bool)
    def requestLog(self, count: int, skip: int, include_all_refs: bool = False):
        """后台分页获取提交,完成发 logReady(repoPath, skip, list),不阻塞主线程。"""
        repo = self._svc.repo_path or ""
        self._log_request_serial += 1
        request_serial = self._log_request_serial
        self._timeline_trace(
            "log.request",
            serial=request_serial,
            count=count,
            skip=skip,
            include_all_refs=include_all_refs,
            repo=repo,
        )

        def work():
            return [
                    _commit_to_dict(c)
                    for c in self._svc.get_graph_log_at(
                        repo, count, skip, include_all_refs
                    )
                ]

        def completed(batch: list) -> None:
            if request_serial != self._log_request_serial:
                self._timeline_trace(
                    "log.result_drop",
                    serial=request_serial,
                    reason="stale_serial",
                    current_serial=self._log_request_serial,
                    skip=skip,
                    batch_length=len(batch),
                )
                return
            if repo != (self._svc.repo_path or ""):
                self._timeline_trace(
                    "log.result_drop",
                    serial=request_serial,
                    reason="repo_changed",
                    skip=skip,
                    batch_length=len(batch),
                    repo=repo,
                    current_repo=self._svc.repo_path or "",
                )
                return
            self._timeline_trace(
                "log.result_emit",
                serial=request_serial,
                skip=skip,
                batch_length=len(batch),
                repo=repo,
            )
            self.logReady.emit(repo, skip, batch)

        def failed(_exc: BaseException) -> None:
            self._timeline_trace(
                "log.failed",
                serial=request_serial,
                skip=skip,
                repo=repo,
            )
            completed([])

        return self._submit_query(
            work,
            label="获取提交历史",
            on_success=completed,
            on_failure=failed,
        )

    @Slot(str, str, bool)
    def requestSearch(
        self, query: str, search_type: str, include_all_refs: bool = False
    ):
        """后台流式搜索提交，先发阶段结果，再发完整结果。"""
        repo = self._svc.repo_path or ""
        self._cancel_active_search()
        self._search_request_serial += 1
        request_serial = self._search_request_serial

        def work():
            task = current_task()
            return [
                    _commit_to_dict(c)
                    for c in self._svc.search_commits_progressively_at(
                        repo,
                        query,
                        search_type,
                        100,
                        include_all_refs,
                        lambda commits: task.report_progress([
                            _commit_to_dict(commit) for commit in commits
                        ]),
                    )
                ]

        def progressed(results: list) -> None:
            if request_serial != self._search_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            self.searchPreviewReady.emit(repo, results)

        def completed(results: list) -> None:
            if request_serial != self._search_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            self.searchReady.emit(repo, results)

        handle = None

        def finished() -> None:
            if self._search_task is handle:
                self._search_task = None

        handle = self._submit_query(
            work,
            label="搜索提交",
            on_success=completed,
            on_failure=lambda _exc: completed([]),
            on_progress=progressed,
            on_finished=finished,
        )
        self._search_task = handle
        return handle

    def _cancel_active_search(self) -> None:
        if self._search_task is not None:
            self._search_task.cancel()
            self._search_task = None

    @Slot()
    def cancelSearch(self) -> None:
        """取消仍在扫描历史的搜索，并使迟到结果失效。"""
        self._search_request_serial += 1
        self._cancel_active_search()

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
        self._branches_request_serial += 1
        request_serial = self._branches_request_serial

        def completed(data: list) -> None:
            if request_serial != self._branches_request_serial:
                return
            if repo != (self._svc.repo_path or ""):
                return
            self.branchesReady.emit(repo, data)

        return self._submit_query(
            lambda: [_branch_to_dict(b) for b in self._svc.get_branches()],
            label="获取分支列表",
            on_success=completed,
            on_failure=lambda _exc: completed([]),
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

    @Slot(str, str, result=QObject)
    def fetchAndCheckoutRemoteBranch(
        self, remote_branch: str, local_branch: str
    ):
        return self._submit_operation(
            "正在获取并检出远程分支...",
            lambda: self._svc.fetch_and_checkout_remote_branch(
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
    def resolveAllWithOurs(self):
        return self._submit_operation(
            "正在使用当前分支版本解决全部冲突...",
            self._svc.resolve_all_conflicts_with_ours,
        )

    @Slot(result=QObject)
    def resolveAllWithTheirs(self):
        return self._submit_operation(
            "正在使用对方分支版本解决全部冲突...",
            self._svc.resolve_all_conflicts_with_theirs,
        )

    @Slot(result=QObject)
    def continueMerge(self):
        return self._submit_operation("正在完成合并...", self._svc.continue_merge)

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
        """后台获取有界提交文件预览。"""
        repo = self._svc.repo_path or ""

        def work() -> tuple[list[dict], int, bool, dict[str, int]]:
            files, total, truncated, status_counts = self._svc.get_commit_files_preview(
                commit_hash
            )
            return [
                _file_change_to_dict(file_change) for file_change in files
            ], total, truncated, status_counts

        return self._submit_query(
            work,
            label="获取提交文件",
            on_success=lambda data: self.commitFilesReady.emit(
                repo, commit_hash, data[0], data[1], data[2], data[3]
            ),
            on_failure=lambda _exc: self.commitFilesReady.emit(
                repo, commit_hash, [], 0, False, {}
            ),
        )

    @Slot(str, str)
    def requestCommitFileDiff(self, commit_hash: str, file_path: str):
        """后台读取单个提交文件的有界 diff。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: self._svc.get_commit_diff(commit_hash, file_path),
            label="获取提交文件 diff",
            on_success=lambda data: self.commitFileDiffReady.emit(
                repo, commit_hash, file_path, str(data)
            ),
            on_failure=lambda _exc: self.commitFileDiffReady.emit(
                repo, commit_hash, file_path, ""
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
    @staticmethod
    def _read_conflict_file_at(
        repo: str, path: str
    ) -> tuple[str, bool]:
        if not repo:
            return "", False
        full_path = os.path.join(repo, path)
        real_path = os.path.realpath(full_path)
        repo_real = os.path.realpath(repo)
        if not real_path.startswith(repo_real + os.sep):
            logger.warning(f"拒绝读取仓库外路径: {path}")
            return "", False
        try:
            with open(real_path, "rb") as handle:
                raw = handle.read(MAX_CONFLICT_FILE_SIZE + 1)
            truncated = len(raw) > MAX_CONFLICT_FILE_SIZE
            content = raw[:MAX_CONFLICT_FILE_SIZE].decode(
                "utf-8", errors="ignore"
            )
            return content, truncated
        except OSError as exc:
            logger.warning(f"读取冲突文件失败 {path}: {exc}")
            return "", False

    @Slot(str, result=str)
    def readConflictFile(self, path: str) -> str:
        """兼容同步调用；QML 使用 requestConflictFile。"""
        return self._read_conflict_file_at(self._svc.repo_path or "", path)[0]

    @Slot(str, result=QObject)
    def requestConflictFile(self, path: str):
        """后台读取有界冲突文件内容。"""
        repo = self._svc.repo_path or ""

        def work() -> tuple[list[str], bool]:
            content, truncated = self._read_conflict_file_at(repo, path)
            lines = content.split('\n')
            line_limit = 5000
            visible_lines = lines[:line_limit]
            return visible_lines, truncated or len(lines) > line_limit

        return self._submit_query(
            work,
            label="读取冲突文件",
            on_success=lambda data: self.conflictFileReady.emit(
                repo, path, data[0], data[1]
            ),
            on_failure=lambda _exc: self.conflictFileReady.emit(
                repo, path, [], False
            ),
        )

    def _repo_rule_file_path(
        self, name: str, repo: str | None = None
    ) -> tuple[Path | None, str]:
        """解析仓库根目录规则文件，并拒绝越界/未知文件名。"""
        repo = repo if repo is not None else self._svc.repo_path
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
        return self._read_repo_rule_file_at(self._svc.repo_path or "", name)

    def _read_repo_rule_file_at(self, repo: str, name: str) -> str:
        path, error = self._repo_rule_file_path(name, repo)
        if path is None:
            if error != "当前没有打开仓库":
                logger.warning(f"读取规则文件被拒绝 {name}: {error}")
            return ""
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_RULE_FILE_SIZE + 1)
            return raw[:MAX_RULE_FILE_SIZE].decode(
                "utf-8", errors="replace"
            ).replace("\r\n", "\n").replace("\r", "\n")
        except FileNotFoundError:
            return ""
        except OSError as e:
            logger.warning(f"读取规则文件失败 {name}: {e}")
            return ""

    @Slot(str, result=QObject)
    def requestRepoRuleFile(self, name: str):
        """后台读取仓库根目录规则文件。"""
        repo = self._svc.repo_path or ""
        return self._submit_query(
            lambda: self._read_repo_rule_file_at(repo, name),
            label=f"读取规则文件 {name}",
            on_success=lambda content: self.repoRuleFileReady.emit(
                repo, name, content
            ),
            on_failure=lambda _exc: self.repoRuleFileReady.emit(
                repo, name, ""
            ),
        )

    @Slot(str, str, result="QVariantList")
    def saveRepoRuleFile(self, name: str, content: str) -> list:
        """兼容同步调用；QML 使用 saveRepoRuleFileAsync。"""
        result = self._save_repo_rule_file_at(
            self._svc.repo_path or "", name, content
        )
        if result[0]:
            self._reset_poll_baseline("save_repo_rule_file")
            self._timeline_trace(
                "statusChanged.emit",
                source="saveRepoRuleFile",
                repo=self._svc.repo_path or "",
            )
            self.statusChanged.emit()
        return result

    def _save_repo_rule_file_at(
        self, repo: str, name: str, content: str
    ) -> list:
        path, error = self._repo_rule_file_path(name, repo)
        if path is None:
            logger.warning(f"保存规则文件被拒绝 {name}: {error}")
            return [False, error]
        if len(content.encode("utf-8")) > MAX_RULE_FILE_SIZE:
            return [False, f"{name} 内容超过 {MAX_RULE_FILE_SIZE // 1024} KiB 上限"]

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

        return [True, f"已保存 {name}"]

    @Slot(str, str, result=QObject)
    def saveRepoRuleFileAsync(self, name: str, content: str):
        """后台原子保存仓库根目录规则文件。"""
        repo = self._svc.repo_path or ""

        def completed(result: list) -> None:
            if result and result[0] and repo == (self._svc.repo_path or ""):
                self._reset_poll_baseline("save_repo_rule_file_async")
                self._timeline_trace(
                    "statusChanged.emit",
                    source="saveRepoRuleFileAsync",
                    repo=repo,
                )
                self.statusChanged.emit()

        return self._submit_query(
            lambda: self._save_repo_rule_file_at(repo, name, content),
            label=f"保存规则文件 {name}",
            on_success=completed,
            on_failure=lambda _exc: completed([False, "保存规则文件失败"]),
        )
