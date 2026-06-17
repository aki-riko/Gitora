# coding: utf-8
"""
GitBridge - GitService 的 QML 对接壳

设计原则(只重构对接层):
- 不改 GitService 任何 git 命令逻辑,组合持有一个 GitService 实例。
- 负责 dataclass(FileChange/CommitInfo/...) -> QML 可消费的 dict/list 转换。
- 把同步方法用 @Slot 暴露;阻塞型操作转发已有的 statusChanged/operationFinished 信号。
"""
from typing import Optional

from PySide6.QtCore import QObject, Slot, Signal, Property

from app.common.git_service import (
    GitService, FileChange, CommitInfo, BranchInfo, ConflictInfo,
)
from app.common.logger import get_logger

logger = get_logger("GitBridge")


def _file_change_to_dict(fc: FileChange) -> dict:
    """FileChange dataclass -> QML 友好 dict"""
    return {
        "path": fc.path,
        "status": fc.status.value,       # 单字符,如 "M"/"A"/"?"
        "statusText": fc.status_text,    # 本地化文本,如 "已修改"
        "staged": fc.staged,
    }


class GitBridge(QObject):
    """暴露给 QML 的 Git 后端门面"""

    # 透传 GitService 的信号(QML 直接 onXxx 连接)
    statusChanged = Signal()
    operationStarted = Signal(str)
    operationFinished = Signal(bool, str)
    progressUpdated = Signal(int, str)
    repoPathChanged = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._svc = GitService(self)
        # 转发底层信号
        self._svc.statusChanged.connect(self.statusChanged)
        self._svc.operationStarted.connect(self.operationStarted)
        self._svc.operationFinished.connect(self.operationFinished)
        self._svc.progressUpdated.connect(self.progressUpdated)

    # ==================== 属性 ====================
    @Property(str, notify=repoPathChanged)
    def repoPath(self) -> str:
        return self._svc.repo_path or ""

    # ==================== 仓库 ====================
    @Slot(str, result=bool)
    def setRepoPath(self, path: str) -> bool:
        ok = self._svc.set_repo_path(path)
        if ok:
            self.repoPathChanged.emit(self._svc.repo_path or "")
        return ok

    # ==================== 状态 ====================
    @Slot(result="QVariantList")
    def getStatus(self) -> list:
        """工作区变更列表 -> [{path, status, statusText, staged}, ...]"""
        return [_file_change_to_dict(fc) for fc in self._svc.get_status()]

    @Slot(result=str)
    def getCurrentBranch(self) -> str:
        return self._svc.get_current_branch()

    # ==================== 仓库维护 ====================
    @Slot(result="QVariantList")
    def cleanPreview(self) -> list:
        """预览将被清理的未跟踪文件 -> [path, ...]"""
        return self._svc.clean_preview()

    @Slot(bool, result="QVariantList")
    def clean(self, include_directories: bool) -> list:
        """清理未跟踪文件,返回 [成功, 消息]"""
        ok, msg = self._svc.clean(include_directories=include_directories)
        return [ok, msg]

    @Slot()
    def gc(self):
        """垃圾回收(异步);结果经 operationStarted/operationFinished 信号回传"""
        self._svc.gc()
