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
_MAX_SCANNED_REPOSITORIES = 5000
_PROGRESS_EVERY_DIRECTORIES = 100


def _list_fixed_drives() -> List[str]:
    """枚举所有固定磁盘根(Windows)。

    ``os.path.isdir`` 会真的去探测盘符:映射到已断开的网络共享时,重定向器要等
    网络超时,单次探测可以阻塞数十秒。因此本函数**只允许在线程池里调用**
    (见 ``_resolve_scan_roots``),绝不能落在 GUI 主线程上。
    """
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.isdir(root):
            drives.append(root)
    return drives


def _resolve_scan_roots(roots: Optional[List[str]]) -> List[str]:
    """确定扫描根目录:显式传入的原样使用,否则枚举固定磁盘根。

    盘符枚举包含磁盘/网络探测,可能长时间阻塞;它必须发生在线程池线程里,
    调用方 ``RepoScanner.start`` 跑在 GUI 主线程上。
    """
    return list(roots) if roots else _list_fixed_drives()


def _scan_repositories(roots: Optional[List[str]]) -> int:
    """在线程池扫描仓库，并通过引擎进度通道发布结果。"""
    task = current_task()
    # 根目录枚举与日志都在池线程内完成:start() 在 GUI 主线程,不能有任何磁盘探测。
    resolved_roots = _resolve_scan_roots(roots)
    logger.info(f"开始扫描 Git 仓库,根目录: {resolved_roots}")
    count = 0
    visited = 0
    for root in resolved_roots:
        task.raise_if_cancelled()
        for dirpath, dirnames, _filenames in os.walk(root, topdown=True):
            task.raise_if_cancelled()
            visited += 1
            # 命中 .git 则记录该目录为仓库,并剪枝(不再深入)
            if ".git" in dirnames or os.path.isdir(os.path.join(dirpath, ".git")):
                count += 1
                task.report_progress(("repo", dirpath))
                if count >= _MAX_SCANNED_REPOSITORIES:
                    return count
                dirnames[:] = []  # 剪枝:不进入仓库内部子目录
                continue
            # 原地过滤要跳过的目录(topdown=True 时修改 dirnames 生效)
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.startswith(".")
            ]
            if visited % _PROGRESS_EVERY_DIRECTORIES == 0:
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

    @Slot("QVariantList", result="QVariantList")
    def mergeWithOpenedRepos(self, opened_repos) -> list:
        """打开记录优先，按当前系统的路径等价规则合并扫描缓存。"""
        return self._cache.merge_prioritized(
            list(opened_repos or []), self._results
        )

    @Slot()
    @Slot("QVariantList")
    def start(self, roots=None):
        """开始扫描;roots 为空则在线程池内枚举固定磁盘。

        本方法由 GUI 主线程调用(QML 定时器),因此这里**不能**做任何磁盘或网络
        探测:根目录枚举推迟到池线程(_scan_repositories)。历史故障记录见
        ``docs/startup-hang-root-cause.md``。
        """
        if self.scanning:
            logger.info("扫描已在进行中,忽略重复请求")
            return
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
