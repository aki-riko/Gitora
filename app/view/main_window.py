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
from .setting_interface import SettingInterface
from ..common.config import cfg
from ..common.icon import Icon
from ..common.signal_bus import signalBus
from ..common import resource


class MainWindow(MSFluentWindow):
    """主窗口 - Git可视化工具"""

    def __init__(self):
        super().__init__()
        self.initWindow()

        # 创建界面
        self.repoInterface = RepoInterface(self)
        self.historyInterface = HistoryInterface(self)
        self.branchInterface = BranchInterface(self)
        self.conflictInterface = ConflictInterface(self)
        self.settingInterface = SettingInterface(self)

        self.connectSignalToSlot()

        # 添加导航项
        self.initNavigation()

    def connectSignalToSlot(self):
        signalBus.micaEnableChanged.connect(self.setMicaEffectEnabled)

    def initNavigation(self):
        # 仓库界面（首页）
        self.addSubInterface(
            self.repoInterface,
            FIF.HOME,
            self.tr('仓库'),
            FIF.HOME_FILL
        )

        # 历史界面
        self.addSubInterface(
            self.historyInterface,
            FIF.HISTORY,
            self.tr('历史')
        )

        # 分支界面
        self.addSubInterface(
            self.branchInterface,
            FIF.DEVELOPER_TOOLS,
            self.tr('分支')
        )

        # 冲突界面
        self.addSubInterface(
            self.conflictInterface,
            FIF.CANCEL,
            self.tr('冲突')
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