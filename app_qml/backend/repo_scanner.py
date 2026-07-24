# coding: utf-8
"""
RepoScanner - 后台扫描磁盘上的 Git 仓库

纯 os.walk 实现,零依赖零下载。由 PrismQML 全局任务池执行,不堵主线程。
剧烈剪枝:跳过 .git 内部、node_modules、系统目录等,找到 .git 即记录并不再深入。
"""
import os
import string
from typing import List, Optional

from PySide6.QtCore import QObject, Signal, Slot, Property
from prismqml import TaskHandle, current_task

from app.common.logger import get_logger
from app.common.prism_task import submit_to_pool
from app.common.scanned_repos import ScannedReposCache

logger = get_logger("RepoScanner")

# 剪枝:这些目录名一律不进入(性能 + 避免噪声)
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "AppData", "Windows", "$Recycle.Bin", "System Volume Information",
    "Program Files", "Program Files (x86)", "ProgramData",
    ".cache", ".cargo", ".rustup", ".gradle", ".m2", ".nuget",
    "target", "build", "dist", "vendor", "Library",
}


def _list_fixed_drives() -> List[str]:
    """枚举所有固定磁盘根(Windows)。"""
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.isdir(root):
            drives.append(root)
    return drives


def _scan_repositories(roots: List[str]) -> int:
    """在线程池扫描仓库，并通过引擎进度通道发布结果。"""
    task = current_task()
    count = 0
    for root in roots:
        task.raise_if_cancelled()
        for dirpath, dirnames, _filenames in os.walk(root, topdown=True):
            task.raise_if_cancelled()
            # 命中 .git 则记录该目录为仓库,并剪枝(不再深入)
            if ".git" in dirnames or os.path.isdir(os.path.join(dirpath, ".git")):
                count += 1
                task.report_progress(("repo", dirpath))
                dirnames[:] = []  # 剪枝:不进入仓库内部子目录
                continue
            # 原地过滤要跳过的目录(topdown=True 时修改 dirnames 生效)
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.startswith(".")
            ]
            task.report_progress(("progress", dirpath))
    return count


class RepoScanner(QObject):
    """暴露给上层的扫描门面"""

    repoFound = Signal(str)
    scanFinished = Signal(int)
    scanProgress = Signal(str)
    scanningChanged = Signal(bool)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        cache: Optional[ScannedReposCache] = None,
    ):
        super().__init__(parent)
        self._cache = cache or ScannedReposCache()
        self._task: Optional[TaskHandle] = None
        self._scanning = False
        self._scan_found_count = 0
        self._results: List[str] = self._cache.get_all()

    @Property(bool, notify=scanningChanged)
    def scanning(self) -> bool:
        return self._scanning

    @Slot(result="QVariantList")
    def getResults(self) -> list:
        """返回已扫描到的仓库列表(累积)。"""
        return list(self._results)

    @Slot()
    @Slot("QVariantList")
    def start(self, roots=None):
        """开始扫描;roots 为空则扫所有固定磁盘。"""
        if self.scanning:
            logger.info("扫描已在进行中,忽略重复请求")
            return
        roots = list(roots) if roots else _list_fixed_drives()
        logger.info(f"开始扫描 Git 仓库,根目录: {roots}")
        self._results = self._cache.get_all()
        self._scan_found_count = 0
        self._scanning = True
        self.scanningChanged.emit(True)
        self._task = submit_to_pool(
            _scan_repositories,
            roots,
            on_success=self._on_finished,
            on_failure=self._on_failed,
            on_progress=self._on_progress,
            on_cancelled=self._on_cancelled,
        )

    @Slot()
    def stop(self):
        if self._task:
            self._task.cancel()

    def shutdown(self):
        """程序退出时请求取消；等待和清理由 PrismQML ``App`` 统一完成。"""
        self.stop()

    def _on_progress(self, update: object) -> None:
        kind, value = update
        if kind == "repo":
            self._on_repo_found(str(value))
        else:
            self.scanProgress.emit(str(value))

    def _on_repo_found(self, path: str):
        self._scan_found_count += 1
        normalized_path, added = self._cache.add(path)
        if added:
            self._results.append(normalized_path)
        self.repoFound.emit(normalized_path)

    def _on_finished(self, count: object):
        logger.info(f"扫描完成,找到 {count} 个仓库")
        self._cache.save()
        self._task = None
        self._scanning = False
        self.scanningChanged.emit(False)
        self.scanFinished.emit(int(count))

    def _on_failed(self, exc: BaseException) -> None:
        logger.warning(f"扫描 Git 仓库失败: {type(exc).__name__}: {exc}")
        self._finish_without_result()

    def _on_cancelled(self) -> None:
        logger.info("Git 仓库扫描已取消")
        self._finish_without_result()

    def _finish_without_result(self) -> None:
        self._cache.save()
        count = self._scan_found_count
        self._task = None
        self._scanning = False
        self.scanningChanged.emit(False)
        self.scanFinished.emit(count)
