# coding:utf-8
from qfluentwidgets import (SwitchSettingCard, FolderListSettingCard,
                            OptionsSettingCard, PushSettingCard,
                            HyperlinkCard, PrimaryPushSettingCard, ScrollArea,
                            ComboBoxSettingCard, ExpandLayout, Theme, CustomColorSettingCard,
                            setTheme, setThemeColor, isDarkTheme, setFont, MessageBox)
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import SettingCardGroup as CardGroup
from qfluentwidgets import InfoBar
from PySide6.QtCore import Qt, Signal, QUrl, QStandardPaths
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import QWidget, QLabel, QFileDialog

from ..common.config import cfg, isWin11
from ..common.setting import HELP_URL, FEEDBACK_URL, AUTHOR, VERSION, YEAR
from ..common.signal_bus import signalBus
from ..common.style_sheet import StyleSheet
from ..common.git_service import gitService


class SettingCardGroup(CardGroup):

   def __init__(self, title: str, parent=None):
       super().__init__(title, parent)
       setFont(self.titleLabel, 14, QFont.Weight.DemiBold)



class SettingInterface(ScrollArea):
    """ Setting interface """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        # setting label
        self.settingLabel = QLabel(self.tr("Settings"), self)

        # personalization
        self.personalGroup = SettingCardGroup(
            self.tr('Personalization'), self.scrollWidget)
        self.micaCard = SwitchSettingCard(
            FIF.TRANSPARENT,
            self.tr('Mica effect'),
            self.tr('Apply semi transparent to windows and surfaces'),
            cfg.micaEnabled,
            self.personalGroup
        )
        self.themeCard = ComboBoxSettingCard(
            cfg.themeMode,
            FIF.BRUSH,
            self.tr('Application theme'),
            self.tr("Change the appearance of your application"),
            texts=[
                self.tr('Light'), self.tr('Dark'),
                self.tr('Use system setting')
            ],
            parent=self.personalGroup
        )
        self.zoomCard = ComboBoxSettingCard(
            cfg.dpiScale,
            FIF.ZOOM,
            self.tr("Interface zoom"),
            self.tr("Change the size of widgets and fonts"),
            texts=[
                "100%", "125%", "150%", "175%", "200%",
                self.tr("Use system setting")
            ],
            parent=self.personalGroup
        )
        self.languageCard = ComboBoxSettingCard(
            cfg.language,
            FIF.LANGUAGE,
            self.tr('Language'),
            self.tr('Set your preferred language for UI'),
            texts=['简体中文', '繁體中文', 'English', self.tr('Use system setting')],
            parent=self.personalGroup
        )

        # remote repository
        self.remoteGroup = SettingCardGroup(
            self.tr("远程仓库"), self.scrollWidget)
        self.remoteCard = PushSettingCard(
            self.tr('管理远程仓库'),
            FIF.CLOUD,
            self.tr('远程仓库'),
            self.tr('添加、删除和修改远程仓库URL'),
            self.remoteGroup
        )
        self.remoteCard.clicked.connect(self._on_manage_remotes)
        
        # repository maintenance
        self.maintenanceGroup = SettingCardGroup(
            self.tr("仓库维护"), self.scrollWidget)
        self.cleanCard = PushSettingCard(
            self.tr('清理未跟踪文件'),
            FIF.DELETE,
            self.tr('清理文件'),
            self.tr('删除所有未被Git跟踪的文件和目录'),
            self.maintenanceGroup
        )
        self.cleanCard.clicked.connect(self._on_clean_files)
        
        self.gcCard = PushSettingCard(
            self.tr('优化仓库'),
            FIF.SYNC,
            self.tr('垃圾回收'),
            self.tr('运行垃圾回收，优化仓库性能'),
            self.maintenanceGroup
        )
        self.gcCard.clicked.connect(self._on_gc)
        
        self.installGitCard = PushSettingCard(
            self.tr('安装Git'),
            FIF.DOWNLOAD,
            self.tr('Git安装'),
            self.tr('打开Git官方下载页面，手动安装Git'),
            self.maintenanceGroup
        )
        self.installGitCard.clicked.connect(self._on_install_git)
        
        # update software
        self.updateSoftwareGroup = SettingCardGroup(
            self.tr("Software update"), self.scrollWidget)
        self.updateOnStartUpCard = SwitchSettingCard(
            FIF.UPDATE,
            self.tr('Check for updates when the application starts'),
            self.tr('The new version will be more stable and have more features'),
            configItem=cfg.checkUpdateAtStartUp,
            parent=self.updateSoftwareGroup
        )

        # application
        self.aboutGroup = SettingCardGroup(self.tr('About'), self.scrollWidget)
        self.aboutCard = PrimaryPushSettingCard(
            self.tr('Check update'),
            ":/app/images/logo.png",
            self.tr('About'),
            '© ' + self.tr('Copyright') + f" {YEAR}, {AUTHOR}. " +
            self.tr('Version') + " " + VERSION,
            self.aboutGroup
        )

        self.__initWidget()

    def __initWidget(self):
        self.resize(1000, 800)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 80, 0, 20)  # 符合QFluentWidget规范
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.setObjectName('settingInterface')

        # initialize style sheet
        setFont(self.settingLabel, 23, QFont.Weight.DemiBold)
        self.scrollWidget.setObjectName('scrollWidget')
        self.settingLabel.setObjectName('settingLabel')
        StyleSheet.SETTING_INTERFACE.apply(self)
        self.scrollWidget.setStyleSheet("QWidget{background:transparent}")

        self.micaCard.setEnabled(isWin11())

        # initialize layout
        self.__initLayout()
        self._connectSignalToSlot()

    def __initLayout(self):
        self.settingLabel.move(36, 30)  # 符合QFluentWidget规范

        self.personalGroup.addSettingCard(self.micaCard)
        self.personalGroup.addSettingCard(self.themeCard)
        self.personalGroup.addSettingCard(self.zoomCard)
        self.personalGroup.addSettingCard(self.languageCard)

        self.updateSoftwareGroup.addSettingCard(self.updateOnStartUpCard)

        self.aboutGroup.addSettingCard(self.aboutCard)

        self.remoteGroup.addSettingCard(self.remoteCard)
        
        self.maintenanceGroup.addSettingCard(self.cleanCard)
        self.maintenanceGroup.addSettingCard(self.gcCard)
        self.maintenanceGroup.addSettingCard(self.installGitCard)
        
        # add setting card group to layout
        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 10, 36, 0)
        # 调整顺序：远程仓库和仓库维护移到个性化上面
        self.expandLayout.addWidget(self.remoteGroup)
        self.expandLayout.addWidget(self.maintenanceGroup)
        self.expandLayout.addWidget(self.personalGroup)
        self.expandLayout.addWidget(self.updateSoftwareGroup)
        self.expandLayout.addWidget(self.aboutGroup)

    def _showRestartTooltip(self):
        """ show restart tooltip """
        InfoBar.success(
            self.tr('Updated successfully'),
            self.tr('Configuration takes effect after restart'),
            duration=1500,
            parent=self
        )

    def _connectSignalToSlot(self):
        """ connect signal to slot """
        cfg.appRestartSig.connect(self._showRestartTooltip)

        # personalization
        cfg.themeChanged.connect(setTheme)
        self.micaCard.checkedChanged.connect(signalBus.micaEnableChanged)

        # check update
        self.aboutCard.clicked.connect(signalBus.checkUpdateSig)
    
    def _on_manage_remotes(self):
        """管理远程仓库"""
        from ..common.git_service import gitService
        
        if not gitService.repo_path:
            InfoBar.warning(
                self.tr('提示'),
                self.tr('请先打开一个Git仓库'),
                duration=2000,
                parent=self
            )
            return
        
        # 异步获取远程仓库信息
        from app.common.async_helper import AsyncTask
        
        def on_success(remotes):
            if not remotes:
                content = self.tr('当前仓库没有配置远程仓库')
            else:
                content = "\n".join([f"{name}: {url}" for name, url in remotes])
            
            # 显示信息对话框
            box = MessageBox(
                self.tr('远程仓库列表'),
                content,
                self
            )
            box.exec()
        
        AsyncTask.run(
            func=gitService.get_remote_info,
            on_success=on_success,
            progress_title='请稍候',
            progress_content='正在获取远程仓库信息...',
            parent=self
        )
    
    def _on_clean_files(self):
        """清理未跟踪文件"""
        if not gitService.repo_path:
            InfoBar.warning(
                self.tr('提示'),
                self.tr('请先打开一个Git仓库'),
                duration=2000,
                parent=self
            )
            return
        
        from .clean_dialog import CleanDialog
        dialog = CleanDialog(self.window())
        if dialog.exec():
            include_dir = dialog.includeDirCheckbox.isChecked()
            success, msg = gitService.clean(include_directories=include_dir)
            if success:
                InfoBar.success(
                    self.tr('成功'),
                    msg,
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.error(
                    self.tr('失败'),
                    msg,
                    duration=3000,
                    parent=self
                )
    
    def _on_gc(self):
        """优化仓库（异步）"""
        if not gitService.repo_path:
            InfoBar.warning(
                self.tr('提示'),
                self.tr('请先打开一个Git仓库'),
                duration=2000,
                parent=self
            )
            return
        
        # 异步执行，会自动显示进度环（通过operationStarted/Finished信号）
        gitService.gc()
    
    def _on_install_git(self):
        """安装Git"""
        from ..common.git_installer import gitInstaller
        
        # 检测Git是否已安装
        installed, version = gitInstaller.check_git_installed()
        if installed:
            InfoBar.success(
                self.tr('提示'),
                f'Git已安装: {version}',
                duration=3000,
                parent=self
            )
            return
        
        # 显示安装引导
        gitInstaller.show_install_guide(self.window())

