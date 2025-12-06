# coding:utf-8
"""
初始化仓库引导窗口
使用GuideWindow实现分步引导
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    TitleLabel, BodyLabel, LineEdit, setFont, ImageLabel,
    PushButton, FluentIcon, InfoBar, InfoBarPosition
)
from qfluentwidgetspro import GuideWindow

from ..common.git_service import gitService


class WelcomeInterface(QWidget):
    """欢迎界面 - 第1步"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(28)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 标题
        self.titleLabel = TitleLabel("初始化Git仓库", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel, 0, Qt.AlignmentFlag.AlignCenter)
        
        # 说明
        self.bodyLabel = BodyLabel(
            "将为您创建一个新的Git仓库，并引导您完成基本配置。\n\n"
            "这包括：\n"
            "• 初始化Git仓库\n"
            "• 配置用户信息（可选）\n"
            "• 添加远程仓库（可选）",
            self
        )
        self.bodyLabel.setWordWrap(True)
        self.bodyLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.bodyLabel, 0, Qt.AlignmentFlag.AlignCenter)


class UserInfoInterface(QWidget):
    """用户信息配置界面 - 第2步"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("配置用户信息", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "设置提交时显示的用户名和邮箱",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        # 提示：可以跳过
        self.skipHintLabel = BodyLabel(
            "💡 提示：如果不填写，点击“下一步”将跳过此步骤",
            self
        )
        self.skipHintLabel.setWordWrap(True)
        self.skipHintLabel.setTextColor(QColor(255, 152, 0), QColor(255, 152, 0))  # 橙色
        layout.addWidget(self.skipHintLabel)
        
        layout.addSpacing(20)
        
        # 用户名
        self.nameLabel = BodyLabel("用户名:", self)
        layout.addWidget(self.nameLabel)
        
        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText("如: Zhang San")
        self.nameEdit.setClearButtonEnabled(True)
        
        layout.addWidget(self.nameEdit)
        
        layout.addSpacing(12)
        
        # 邮箱
        self.emailLabel = BodyLabel("邮箱:", self)
        layout.addWidget(self.emailLabel)
        
        self.emailEdit = LineEdit(self)
        self.emailEdit.setPlaceholderText("如: zhangsan@example.com")
        self.emailEdit.setClearButtonEnabled(True)
        
        # 异步加载全局配置
        from app.common.async_helper import SimpleAsyncTask
        
        def on_loaded(result):
            name, email = result
            if name:
                self.nameEdit.setText(name)
            if email:
                self.emailEdit.setText(email)
        
        SimpleAsyncTask.run(gitService.get_user_info, on_loaded)
        
        layout.addWidget(self.emailEdit)
        
        layout.addStretch()
    
    def get_user_info(self) -> tuple[str, str]:
        """获取用户信息"""
        return self.nameEdit.text().strip(), self.emailEdit.text().strip()


class RemoteInterface(QWidget):
    """远程仓库配置界面 - 必填模式（用于修复/配置远程仓库）"""
    
    def __init__(self, parent=None, existing_remotes=None):
        """
        Args:
            parent: 父窗口
            existing_remotes: 已存在的远程列表
        """
        super().__init__(parent=parent)
        self.existing_remotes = existing_remotes or []
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("添加远程仓库", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "配置远程仓库用于推送代码到GitHub、GitLab等平台",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        layout.addSpacing(20)
        
        # 远程名称
        self.nameLabel = BodyLabel("远程名称: *", self)
        layout.addWidget(self.nameLabel)
        
        self.nameEdit = LineEdit(self)
        self.nameEdit.setText("origin")
        self.nameEdit.setPlaceholderText("通常使用 origin（必填）")
        self.nameEdit.textChanged.connect(self._validate_inputs)
        layout.addWidget(self.nameEdit)
        
        layout.addSpacing(12)
        
        # 远程URL
        self.urlLabel = BodyLabel("远程URL: *", self)
        layout.addWidget(self.urlLabel)
        
        self.urlEdit = LineEdit(self)
        self.urlEdit.setPlaceholderText("如: https://github.com/user/repo.git 或 git@github.com:user/repo.git")
        self.urlEdit.setClearButtonEnabled(True)
        self.urlEdit.textChanged.connect(self._validate_inputs)
        layout.addWidget(self.urlEdit)
        
        # SSH格式说明
        self.sshHintLabel = BodyLabel(
            "🔑 支持HTTPS和SSH两种格式",
            self
        )
        self.sshHintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.sshHintLabel)
        
        # 显示已存在的远程列表
        if self.existing_remotes:
            self.existingLabel = BodyLabel(
                f"📋 已存在的远程: {', '.join(self.existing_remotes)}",
                self
            )
            self.existingLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
            layout.addWidget(self.existingLabel)
        
        # 实时验证反馈
        layout.addSpacing(12)
        self.validationLabel = BodyLabel("", self)
        self.validationLabel.setWordWrap(True)
        layout.addWidget(self.validationLabel)
        
        layout.addStretch()
        
        # 初始验证
        self._validate_inputs()
    
    def _validate_inputs(self):
        """实时验证输入"""
        name = self.nameEdit.text().strip()
        url = self.urlEdit.text().strip()
        
        # 移除错误提示，禁用按钮已经足够提示用户
        if not name or not url or not self._is_valid_git_url(url):
            self.validationLabel.setText("")  # 清空提示
            return False
        elif name in self.existing_remotes:
            self.validationLabel.setText(f"⚠️ 远程名称 '{name}' 已存在，将会覆盖URL")
            self.validationLabel.setTextColor(QColor(255, 152, 0), QColor(255, 152, 0))
            return True
        else:
            self.validationLabel.setText("✅ 信息填写完整")
            self.validationLabel.setTextColor(QColor(76, 175, 80), QColor(76, 175, 80))
            return True
    
    def _is_valid_git_url(self, url: str) -> bool:
        """验证Git URL格式"""
        if not url:
            return False
        
        # HTTPS: https://github.com/user/repo.git
        if url.startswith('https://') or url.startswith('http://'):
            # 基本检查：至少包含域名和路径
            parts = url.split('/')
            return len(parts) >= 4 and '.' in parts[2]
        
        # SSH: git@github.com:user/repo.git
        if url.startswith('git@') or url.startswith('ssh://'):
            # SSH格式检查
            if url.startswith('git@'):
                # git@host:path 格式
                return ':' in url and len(url.split(':')) == 2 and '/' in url.split(':')[1]
            else:
                # ssh://git@host/path 格式
                return len(url.split('/')) >= 4
        
        # Git协议: git://github.com/user/repo.git
        if url.startswith('git://'):
            parts = url.split('/')
            return len(parts) >= 4
        
        # 本地路径或文件URL
        if url.startswith('file://') or url.startswith('/'):
            return True
        
        return False
    
    def get_remote_info(self) -> tuple[str, str]:
        """获取远程仓库信息"""
        return self.nameEdit.text().strip(), self.urlEdit.text().strip()
    
    def is_valid(self) -> bool:
        """验证是否可以继续下一步"""
        name, url = self.get_remote_info()
        return bool(name and url)


class OptionalRemoteInterface(QWidget):
    """可选的远程仓库配置界面 - 用于初始化仓库向导"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("添加远程仓库", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "配置远程仓库用于推送代码到GitHub、GitLab等平台",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        # 可选提示
        self.skipHintLabel = BodyLabel(
            "💡 提示：如果暂时不配置，点击'下一步'将跳过此步骤",
            self
        )
        self.skipHintLabel.setWordWrap(True)
        self.skipHintLabel.setTextColor(QColor(255, 152, 0), QColor(255, 152, 0))  # 橙色
        layout.addWidget(self.skipHintLabel)
        
        layout.addSpacing(20)
        
        # 远程名称
        self.nameLabel = BodyLabel("远程名称:", self)
        layout.addWidget(self.nameLabel)
        
        self.nameEdit = LineEdit(self)
        self.nameEdit.setText("origin")
        self.nameEdit.setPlaceholderText("通常使用 origin")
        layout.addWidget(self.nameEdit)
        
        layout.addSpacing(12)
        
        # 远程URL
        self.urlLabel = BodyLabel("远程URL:", self)
        layout.addWidget(self.urlLabel)
        
        self.urlEdit = LineEdit(self)
        self.urlEdit.setPlaceholderText("如: https://github.com/user/repo.git 或 git@github.com:user/repo.git")
        self.urlEdit.setClearButtonEnabled(True)
        layout.addWidget(self.urlEdit)
        
        # SSH格式说明
        self.sshHintLabel = BodyLabel(
            "🔑 支持HTTPS和SSH两种格式",
            self
        )
        self.sshHintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.sshHintLabel)
        
        layout.addStretch()
    
    def get_remote_info(self) -> tuple[str, str]:
        """获取远程仓库信息"""
        return self.nameEdit.text().strip(), self.urlEdit.text().strip()


class FinalInterface(QWidget):
    """完成界面 - 第4步"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(28)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 标题
        self.titleLabel = TitleLabel("配置完成！", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel, 0, Qt.AlignmentFlag.AlignCenter)
        
        # 说明
        self.bodyLabel = BodyLabel(
            "Git仓库已成功初始化并完成配置。\n\n"
            "您现在可以开始使用Gitess管理您的代码了！",
            self
        )
        self.bodyLabel.setWordWrap(True)
        self.bodyLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.bodyLabel, 0, Qt.AlignmentFlag.AlignCenter)


class InitRepoGuide(GuideWindow):
    """初始化仓库引导窗口"""
    
    completed = Signal(str)  # 完成信号，传递仓库路径
    
    def __init__(self, repo_path: str):
        super().__init__()  # GuideWindow不需要parent参数
        self.repo_path = repo_path
        
        self.setWindowTitle("初始化Git仓库")
        self.resize(800, 500)
        
        # 添加引导页面
        self.welcomePage = WelcomeInterface()
        self.userInfoPage = UserInfoInterface()
        self.remotePage = OptionalRemoteInterface()  # 使用可选版本
        self.finalPage = FinalInterface()
        
        self.addPage(self.welcomePage)
        self.addPage(self.userInfoPage)
        self.addPage(self.remotePage)
        self.addPage(self.finalPage)
        
        # 连接完成信号 - 点击最后一步的“开始使用”按钮时触发
        self.appStarted.connect(self._on_guide_completed)
        
        # 连接页面切换信号，用于验证
        self.currentIndexChanged.connect(self._on_page_changed)
    
    def _on_page_changed(self, index: int):
        """页面切换时验证上一页的输入"""
        # 第1页（欢迎）→ 第2页（用户信息）：无需验证
        # 第2页 → 第3页：验证用户信息
        if index == 2:  # 切换到第3页时
            name, email = self.userInfoPage.get_user_info()
            if name and not email:
                # 填了用户名但没填邮箱
                InfoBar.warning(
                    "提示",
                    "请同时填写用户名和邮箱，或者两者都不填",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
            elif email and not name:
                # 填了邮箱但没填用户名
                InfoBar.warning(
                    "提示",
                    "请同时填写用户名和邮箱，或者两者都不填",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
        
        # 第3页 → 第4页：验证远程仓库
        elif index == 3:  # 切换到第4页时
            remote_name, remote_url = self.remotePage.get_remote_info()
            if remote_name and not remote_url:
                InfoBar.warning(
                    "提示",
                    "请同时填写远程名称和URL，或者两者都不填",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
            elif remote_url and not remote_name:
                InfoBar.warning(
                    "提示",
                    "请同时填写远程名称和URL，或者两者都不填",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
    
    def _on_guide_completed(self):
        """引导完成 - appStarted信号触发"""
        # 异步保存配置
        from app.common.async_helper import SimpleAsyncTask
        
        def save_config():
            # 配置用户信息（如果填写了）
            name, email = self.userInfoPage.get_user_info()
            if name and email:
                gitService.set_user_info(name, email, global_scope=False)
            
            # 添加远程仓库（如果填写了）
            remote_name, remote_url = self.remotePage.get_remote_info()
            if remote_name and remote_url:
                gitService.add_remote(remote_name, remote_url)
            
            return True
        
        def on_saved(result):
            # 发送完成信号
            self.completed.emit(self.repo_path)
            # 关闭引导窗口
            self.close()
        
        SimpleAsyncTask.run(save_config, on_saved)
