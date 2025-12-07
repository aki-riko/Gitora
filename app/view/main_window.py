# coding: utf-8
"""
Gitess 主窗口
集成仓库、历史、分支、冲突、设置界面
"""
from PySide6.QtCore import QUrl, QSize
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import QApplication

from qfluentwidgets import NavigationItemPosition, MSFluentWindow, SplashScreen
from qfluentwidgets import FluentIcon as FIF

from .repo_interface import RepoInterface
from .history_interface import HistoryInterface
from .branch_interface import BranchInterface
from .conflict_interface import ConflictInterface
from .tag_interface import TagInterface
from .setting_interface import SettingInterface
from ..common.config import cfg
from ..common.icon import Icon
from ..common.signal_bus import signalBus
from ..common import resource
from ..common.logger import get_logger

logger = get_logger("MainWindow")


class MainWindow(MSFluentWindow):
    """主窗口 - Git可视化工具"""

    def __init__(self):
        super().__init__()
        logger.info("初始化主窗口")
        self.initWindow()

        # 创建界面
        self.repoInterface = RepoInterface(self)
        self.historyInterface = HistoryInterface(self)
        self.branchInterface = BranchInterface(self)
        self.conflictInterface = ConflictInterface(self)
        self.tagInterface = TagInterface(self)
        self.settingInterface = SettingInterface(self)

        self.connectSignalToSlot()

        # 添加导航项
        self.initNavigation()

    def connectSignalToSlot(self):
        signalBus.micaEnableChanged.connect(self.setMicaEffectEnabled)
        
        # 统一处理Git操作进度信号
        from ..common.git_service import gitService
        gitService.operationStarted.connect(self._on_operation_started)
        gitService.operationFinished.connect(self._on_operation_finished)
    
    def _on_operation_started(self, msg: str):
        """操作开始 - 显示进度环"""
        logger.info(f"Git操作开始: {msg}")
        from qfluentwidgetspro import ProgressInfoBar
        from qfluentwidgets import InfoBarPosition
        from PySide6.QtCore import Qt
        
        # 关闭之前的进度环
        if hasattr(self, '_progress_bar') and self._progress_bar:
            try:
                self._progress_bar.close()
            except Exception as e:
                logger.warning(f"关闭进度环失败: {e}")
        
        # 显示新的进度环
        self._progress_bar = ProgressInfoBar.create(
            title='请勿离开',
            content=msg,
            orient=Qt.Orientation.Horizontal,
            isClosable=False,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self
        )
    
    def _on_operation_finished(self, success: bool, msg: str):
        """操作完成 - 更新进度环状态"""
        if success:
            logger.info(f"Git操作成功: {msg}")
        else:
            logger.error(f"Git操作失败: {msg}")
        
        if hasattr(self, '_progress_bar') and self._progress_bar:
            try:
                if success:
                    self._progress_bar.setTitle('成功')
                    self._progress_bar.setContent(msg)
                    self._progress_bar.success(duration=2000)
                else:
                    self._progress_bar.setTitle('失败')
                    self._progress_bar.setContent(msg)
                    self._progress_bar.error(duration=3000)
            except Exception as e:
                logger.warning(f"更新进度环失败: {e}")

    def initNavigation(self):
        # 仓库界面（首页）
        self.addSubInterface(
            self.repoInterface,
            Icon.GIT_REPOSITORY,  # Git专用仓库图标
            self.tr('仓库')
        )

        # 历史界面
        self.addSubInterface(
            self.historyInterface,
            Icon.GIT_REPOSITORY_COMMITS,  # Git专用提交历史图标
            self.tr('历史')
        )

        # 分支界面
        self.addSubInterface(
            self.branchInterface,
            Icon.GIT_BRANCH,  # Git专用分支图标
            self.tr('分支')
        )

        # 冲突界面
        self.addSubInterface(
            self.conflictInterface,
            Icon.GIT_FORK,  # 使用Git专用冲突图标
            self.tr('冲突')
        )

        # Tag界面
        self.addSubInterface(
            self.tagInterface,
            FIF.TAG,
            self.tr('Tag')
        )

        # 设置界面（底部）
        self.addSubInterface(
            self.settingInterface,
            Icon.SETTINGS,
            self.tr('设置'),
            Icon.SETTINGS_FILLED,
            NavigationItemPosition.BOTTOM
        )

        self.splashScreen.finish()

    def initWindow(self):
        self.resize(1200, 800)
        self.setMinimumWidth(900)
        self.setWindowIcon(QIcon(':/app/images/logo.png'))
        self.setWindowTitle('Gitess - Git可视化工具')

        self.setCustomBackgroundColor(QColor(240, 244, 249), QColor(32, 32, 32))
        self.setMicaEffectEnabled(cfg.get(cfg.micaEnabled))

        # 创建启动画面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(106, 106))
        self.splashScreen.raise_()

        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)
        self.show()
        QApplication.processEvents()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'splashScreen'):
            self.splashScreen.resize(self.size())