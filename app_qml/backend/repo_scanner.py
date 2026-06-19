# coding: utf-8
"""
RepoScanner - 后台扫描磁盘上的 Git 仓库

纯 os.walk 实现,零依赖零下载。在 QThread 后台运行,不堵主线程。
剧烈剪枝:跳过 .git 内部、node_modules、系统目录等,找到 .git 即记录并不再深入。
"""
import os
import string
from typing import List, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot, Property

from app.common.logger import get_logger

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


class _ScanWorker(QThread):
    """后台扫描线程"""

    repoFound = Signal(str)        # 找到一个仓库(路径)
    finished = Signal(int)         # 扫描完成(总数)
    progress = Signal(str)         # 当前扫描目录(用于 UI 提示)

    def __init__(self, roots: List[str], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._roots = roots
        self._stop = False
        self._count = 0

    def stop(self):
        self._stop = True

    def run(self):
        for root in self._roots:
            if self._stop:
                break
            self._scan_root(root)
        self.finished.emit(self._count)

    def _scan_root(self, root: str):
        for dirpath, dirnames, _filenames in os.walk(root, topdown=True):
            if self._stop:
                return
            # 命中 .git 则记录该目录为仓库,并剪枝(不再深入)
            if ".git" in dirnames or os.path.isdir(os.path.join(dirpath, ".git")):
                self._count += 1
                self.repoFound.emit(dirpath)
                dirnames[:] = []  # 剪枝:不进入仓库内部子目录
                continue
            # 原地过滤要跳过的目录(topdown=True 时修改 dirnames 生效)
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.startswith(".")
            ]
            self.progress.emit(dirpath)


class RepoScanner(QObject):
    """暴露给上层的扫描门面"""

    repoFound = Signal(str)
    scanFinished = Signal(int)
    scanProgress = Signal(str)
    scanningChanged = Signal(bool)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._worker: Optional[_ScanWorker] = None
        self._results: List[str] = []

    @Property(bool, notify=scanningChanged)
    def scanning(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

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
        self._results = []
        self._worker = _ScanWorker(roots, self)
        self._worker.repoFound.connect(self._on_repo_found)
        self._worker.finished.connect(self._on_finished)
        self._worker.progress.connect(self.scanProgress)
        self.scanningChanged.emit(True)
        self._worker.start()

    @Slot()
    def stop(self):
        if self._worker:
            self._worker.stop()

    def shutdown(self):
        """程序退出时调用:停止并等待扫描线程结束,避免 QThread 被销毁时仍在运行。"""
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)  # 最多等 3s

    def _on_repo_found(self, path: str):
        self._results.append(path)
        self.repoFound.emit(path)

    def _on_finished(self, count: int):
        logger.info(f"扫描完成,找到 {count} 个仓库")
        self.scanningChanged.emit(False)
        self.scanFinished.emit(count)
