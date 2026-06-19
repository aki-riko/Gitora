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


class GitBridge(QObject):
    """暴露给 QML 的 Git 后端门面"""

    # 透传 GitService 的信号(QML 直接 onXxx 连接)
    statusChanged = Signal()
    operationStarted = Signal(str)
    operationFinished = Signal(bool, str)
    progressUpdated = Signal(int, str)
    repoPathChanged = Signal(str)
    repoOpened = Signal(bool, str)   # 异步打开完成(成功, 路径/错误消息)
    statusReady = Signal(str, "QVariantList")  # 后台状态就绪(repoPath, 变更列表)
    branchReady = Signal(str, str)             # 后台当前分支就绪(repoPath, 分支)
    logReady = Signal(str, int, "QVariantList")    # 后台提交分页就绪(repoPath, skip, 批次)
    searchReady = Signal(str, "QVariantList")       # 后台搜索结果就绪(repoPath, 结果)

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
            from app.common.recent_repos import recentReposManager
            recentReposManager.add(self._svc.repo_path or path)
            self.repoPathChanged.emit(self._svc.repo_path or "")
        return ok

    @Slot(str)
    def openRepoAsync(self, path: str):
        """后台打开仓库,不阻塞主线程;完成后发 repoOpened(ok, path/err) +(成功时)statusChanged。"""
        import threading

        def work():
            try:
                ok = self._svc.set_repo_path(path)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"打开仓库失败 {path}: {e}")
                ok = False
            if ok:
                from app.common.recent_repos import recentReposManager
                recentReposManager.add(self._svc.repo_path or path)
                # 信号跨线程 emit 是线程安全的(排队到主线程)
                self.repoPathChanged.emit(self._svc.repo_path or "")
                self.repoOpened.emit(True, self._svc.repo_path or path)
                self.statusChanged.emit()
            else:
                self.repoOpened.emit(False, path)

        threading.Thread(target=work, daemon=True).start()

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
    @Slot(result="QVariantList")
    def getStatus(self) -> list:
        """工作区变更列表 -> [{path, status, statusText, staged}, ...]"""
        return [_file_change_to_dict(fc) for fc in self._svc.get_status()]

    @Slot()
    def requestStatus(self):
        """后台获取工作区状态,完成发 statusReady(repoPath,list)+branchReady(repoPath,str)。"""
        import threading
        repo = self._svc.repo_path or ""

        def work():
            try:
                changes = [_file_change_to_dict(fc) for fc in self._svc.get_status()]
                branch = self._svc.get_current_branch()
            except Exception as e:  # noqa: BLE001
                logger.warning(f"获取状态失败: {e}")
                changes, branch = [], ""
            self.statusReady.emit(repo, changes)
            self.branchReady.emit(repo, branch)

        threading.Thread(target=work, daemon=True).start()

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

    # ==================== 暂存 / 取消暂存 ====================
    @Slot(str, result=bool)
    def stageFile(self, path: str) -> bool:
        return self._svc.stage_file(path)

    @Slot(str, result=bool)
    def unstageFile(self, path: str) -> bool:
        return self._svc.unstage_file(path)

    @Slot(result=bool)
    def stageAll(self) -> bool:
        return self._svc.stage_all()

    @Slot(result=bool)
    def unstageAll(self) -> bool:
        return self._svc.unstage_all()

    @Slot(str, result=bool)
    def discardFile(self, path: str) -> bool:
        return self._svc.discard_file(path)

    # ==================== 差异 ====================
    @Slot(str, bool, result=str)
    def getDiff(self, path: str, staged: bool) -> str:
        return self._svc.get_diff(path, staged)

    # ==================== 提交 ====================
    @Slot(str, result="QVariantList")
    def commit(self, message: str) -> list:
        ok, msg = self._svc.commit(message)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def amendCommit(self, message: str) -> list:
        ok, msg = self._svc.amend_commit(message)
        return [ok, msg]

    # ==================== 远程同步(异步,经 operationFinished 回传) ====================
    @Slot()
    def push(self):
        self._svc.push()

    @Slot()
    def pushForce(self):
        self._svc.push(force=True)

    @Slot()
    def pull(self):
        self._svc.pull()

    @Slot()
    def pullRebase(self):
        self._svc.pull(rebase=True)

    @Slot()
    def fetch(self):
        self._svc.fetch()

    @Slot(str)
    def quickCommitPush(self, message: str):
        """一键提交推送(异步);结果经 operationStarted/progressUpdated/operationFinished 回传"""
        self._svc.quick_commit_push(message)

    @Slot(result="QVariantList")
    def getRemoteInfo(self) -> list:
        """远程列表 -> [{name, url}, ...]"""
        return [{"name": name, "url": url} for name, url in self._svc.get_remote_info()]

    # ==================== 提交历史 ====================
    @Slot(int, int, bool, result="QVariantList")
    def getLog(self, count: int, skip: int, fast_mode: bool) -> list:
        """提交历史(分页) -> [{hash, shortHash, author, ...}, ...]"""
        return [_commit_to_dict(c) for c in self._svc.get_log(count, skip, fast_mode)]

    @Slot(int, int)
    def requestLog(self, count: int, skip: int):
        """后台分页获取提交,完成发 logReady(repoPath, skip, list),不阻塞主线程。"""
        import threading
        repo = self._svc.repo_path or ""

        def work():
            try:
                fast = self._svc.is_large_repo()
                batch = [_commit_to_dict(c) for c in self._svc.get_log(count, skip, fast)]
            except Exception as e:  # noqa: BLE001
                logger.warning(f"获取提交历史失败: {e}")
                batch = []
            self.logReady.emit(repo, skip, batch)

        threading.Thread(target=work, daemon=True).start()

    @Slot(str, str)
    def requestSearch(self, query: str, search_type: str):
        """后台搜索提交,完成发 searchReady(repoPath, list)。"""
        import threading
        repo = self._svc.repo_path or ""

        def work():
            try:
                results = [_commit_to_dict(c) for c in self._svc.search_commits(query, search_type, 100)]
            except Exception as e:  # noqa: BLE001
                logger.warning(f"搜索提交失败: {e}")
                results = []
            self.searchReady.emit(repo, results)

        threading.Thread(target=work, daemon=True).start()

    @Slot(result=bool)
    def isLargeRepo(self) -> bool:
        return self._svc.is_large_repo()

    @Slot(str, str, int, result="QVariantList")
    def searchCommits(self, query: str, search_type: str, count: int) -> list:
        return [_commit_to_dict(c) for c in self._svc.search_commits(query, search_type, count)]

    @Slot(str, result=int)
    def getCommitCountAfter(self, commit_hash: str) -> int:
        return self._svc.get_commit_count_after(commit_hash)

    @Slot(str, result="QVariantList")
    def checkoutCommit(self, commit_hash: str) -> list:
        ok, msg = self._svc.checkout_branch(commit_hash)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def revertCommit(self, commit_hash: str) -> list:
        ok, msg = self._svc.revert_commit(commit_hash)
        return [ok, msg]

    @Slot(str, str, result="QVariantList")
    def resetToCommit(self, commit_hash: str, mode: str) -> list:
        ok, msg = self._svc.reset_to_commit(commit_hash, mode)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def cherryPick(self, commit_hash: str) -> list:
        ok, msg = self._svc.cherry_pick(commit_hash)
        return [ok, msg]

    # ==================== 分支 ====================
    @Slot(result="QVariantList")
    def getBranches(self) -> list:
        return [_branch_to_dict(b) for b in self._svc.get_branches()]

    @Slot(str, bool, result="QVariantList")
    def createBranch(self, branch: str, checkout: bool) -> list:
        ok, msg = self._svc.create_branch(branch, checkout)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def checkoutBranch(self, branch: str) -> list:
        ok, msg = self._svc.checkout_branch(branch)
        return [ok, msg]

    @Slot(str, bool, result="QVariantList")
    def deleteBranch(self, branch: str, force: bool) -> list:
        ok, msg = self._svc.delete_branch(branch, force)
        return [ok, msg]

    @Slot(str)
    def mergeBranch(self, branch: str):
        """合并分支(异步);结果经 operationFinished 回传"""
        self._svc.merge_branch(branch)

    @Slot(result="QVariantList")
    def pruneRemote(self) -> list:
        ok, msg = self._svc.prune_remote()
        return [ok, msg]

    # ==================== 冲突 ====================
    @Slot(result=bool)
    def isMerging(self) -> bool:
        return self._svc.is_merging()

    @Slot(result="QVariantList")
    def getConflicts(self) -> list:
        return [_conflict_to_dict(c) for c in self._svc.get_conflicts()]

    @Slot(str, result="QVariantList")
    def resolveWithOurs(self, path: str) -> list:
        ok, msg = self._svc.resolve_conflict_with_ours(path)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def resolveWithTheirs(self, path: str) -> list:
        ok, msg = self._svc.resolve_conflict_with_theirs(path)
        return [ok, msg]

    @Slot(result="QVariantList")
    def abortMerge(self) -> list:
        ok, msg = self._svc.abort_merge()
        return [ok, msg]

    # ==================== Stash ====================
    @Slot(result="QVariantList")
    def stashList(self) -> list:
        """stash 列表 -> [{id, message}, ...]"""
        return [{"id": sid, "message": msg} for sid, msg in self._svc.stash_list()]

    @Slot(str, result="QVariantList")
    def stashSave(self, message: str) -> list:
        ok, msg = self._svc.stash_save(message)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def stashPop(self, stash_id: str) -> list:
        ok, msg = self._svc.stash_pop(stash_id)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def stashApply(self, stash_id: str) -> list:
        ok, msg = self._svc.stash_apply(stash_id)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def stashDrop(self, stash_id: str) -> list:
        ok, msg = self._svc.stash_drop(stash_id)
        return [ok, msg]

    @Slot(result="QVariantList")
    def stashClear(self) -> list:
        ok, msg = self._svc.stash_clear()
        return [ok, msg]

    # ==================== Tag ====================
    @Slot(result="QVariantList")
    def getTags(self) -> list:
        """tag 列表 -> [{name, hash, message}, ...]"""
        return [{"name": n, "hash": h, "message": m} for n, h, m in self._svc.get_tags()]

    @Slot(str, str, result="QVariantList")
    def createTag(self, name: str, message: str) -> list:
        ok, msg = self._svc.create_tag(name, message)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def deleteTag(self, name: str) -> list:
        ok, msg = self._svc.delete_tag(name)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def pushTag(self, name: str) -> list:
        ok, msg = self._svc.push_tag(name)
        return [ok, msg]

    @Slot(result="QVariantList")
    def pushAllTags(self) -> list:
        ok, msg = self._svc.push_all_tags()
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def checkoutTag(self, name: str) -> list:
        ok, msg = self._svc.checkout_tag(name)
        return [ok, msg]

    # ==================== 初始化 / 克隆 ====================
    @Slot(str, result="QVariantList")
    def initRepo(self, path: str) -> list:
        ok, msg = self._svc.init(path)
        return [ok, msg]

    @Slot(str, str)
    def clone(self, url: str, path: str):
        """克隆(异步);结果经 operationFinished 回传"""
        self._svc.clone(url, path)

    # ==================== 用户信息 / 远程 ====================
    @Slot(result="QVariantList")
    def getUserInfo(self) -> list:
        """全局用户配置 -> [name, email]"""
        name, email = self._svc.get_user_info()
        return [name, email]

    @Slot(str, str, bool, result="QVariantList")
    def setUserInfo(self, name: str, email: str, global_scope: bool) -> list:
        ok, msg = self._svc.set_user_info(name, email, global_scope)
        return [ok, msg]

    @Slot(str, str, result="QVariantList")
    def addRemote(self, name: str, url: str) -> list:
        ok, msg = self._svc.add_remote(name, url)
        return [ok, msg]

    @Slot(str, result="QVariantList")
    def removeRemote(self, name: str) -> list:
        ok, msg = self._svc.remove_remote(name)
        return [ok, msg]

    @Slot(str, str, result="QVariantList")
    def setRemoteUrl(self, name: str, url: str) -> list:
        ok, msg = self._svc.set_remote_url(name, url)
        return [ok, msg]

    @Slot(str, result=str)
    def getRemoteUrl(self, name: str) -> str:
        return self._svc.get_remote_url(name)

    # ==================== 文件历史 ====================
    @Slot(str, int, result="QVariantList")
    def getFileHistory(self, path: str, count: int) -> list:
        return [_commit_to_dict(c) for c in self._svc.get_file_history(path, count)]

    @Slot(str, str, result=str)
    def getFileContentAtCommit(self, path: str, commit_hash: str) -> str:
        return self._svc.get_file_content_at_commit(path, commit_hash)

    @Slot(str, str, str, result=str)
    def diffFileBetweenCommits(self, path: str, c1: str, c2: str) -> str:
        return self._svc.diff_file_between_commits(path, c1, c2)

    # ==================== 提交详情 ====================
    @Slot(str, result="QVariantMap")
    def getCommitDetail(self, commit_hash: str) -> dict:
        c = self._svc.get_commit_detail(commit_hash)
        return _commit_to_dict(c) if c else {}

    @Slot(str, result="QVariantList")
    def getCommitFiles(self, commit_hash: str) -> list:
        return [_file_change_to_dict(fc) for fc in self._svc.get_commit_files(commit_hash)]

    @Slot(str, result=str)
    def getCommitDiff(self, commit_hash: str) -> str:
        return self._svc.get_commit_diff(commit_hash)

    # ==================== Reflog ====================
    @Slot(int, result="QVariantList")
    def getReflog(self, count: int) -> list:
        """reflog -> [{hash, ref, message}, ...]"""
        return [{"hash": h, "ref": r, "message": m} for h, r, m in self._svc.get_reflog(count)]

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
