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
from ..common.logger import get_logger

logger = get_logger("InitRepoGuide")


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
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("添加远程仓库", self)
        setFont(self.titleLabel, 24, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "配置远程仓库用于推送代码到GitHub、GitLab等平台",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        layout.addSpacing(12)
        
        # 远程名称
        self.nameLabel = BodyLabel("远程名称: *", self)
        layout.addWidget(self.nameLabel)
        
        self.nameEdit = LineEdit(self)
        self.nameEdit.setText("origin")
        self.nameEdit.setPlaceholderText("通常使用 origin（必填）")
        self.nameEdit.textChanged.connect(self._validate_inputs)
        layout.addWidget(self.nameEdit)
        
        layout.addSpacing(8)
        
        # 协议选择
        from qfluentwidgets import SegmentedWidget
        self.protocolLabel = BodyLabel("协议类型: *", self)
        layout.addWidget(self.protocolLabel)
        
        self.protocolSegmented = SegmentedWidget(self)
        self.protocolSegmented.addItem("https", "HTTPS", lambda: self._on_protocol_changed("https"))
        self.protocolSegmented.addItem("git", "SSH", lambda: self._on_protocol_changed("git"))
        self.protocolSegmented.setCurrentItem("https")
        layout.addWidget(self.protocolSegmented)
        
        layout.addSpacing(8)
        
        # 第1行：主机名 + SSH端口（一行显示）
        host_port_layout = QHBoxLayout()
        host_port_layout.setSpacing(12)
        
        # 主机名
        host_container = QVBoxLayout()
        host_container.setSpacing(4)
        self.hostLabel = BodyLabel("主机名: *", self)
        self.hostEdit = LineEdit(self)
        self.hostEdit.setPlaceholderText("如: github.com")
        self.hostEdit.setClearButtonEnabled(True)
        host_container.addWidget(self.hostLabel)
        host_container.addWidget(self.hostEdit)
        host_port_layout.addLayout(host_container, 3)
        
        # SSH端口（仅SSH显示）
        port_container = QVBoxLayout()
        port_container.setSpacing(4)
        self.sshPortLabel = BodyLabel("SSH端口:", self)
        self.sshPortEdit = LineEdit(self)
        self.sshPortEdit.setText("22")
        self.sshPortEdit.setPlaceholderText("默认: 22")
        self.sshPortEdit.setClearButtonEnabled(True)
        port_container.addWidget(self.sshPortLabel)
        port_container.addWidget(self.sshPortEdit)
        host_port_layout.addLayout(port_container, 1)
        
        layout.addLayout(host_port_layout)
        
        # 初始隐藏SSH端口
        self.sshPortLabel.hide()
        self.sshPortEdit.hide()
        
        layout.addSpacing(8)
        
        # 第2行：用户名 + 仓库名（一行显示）
        user_repo_layout = QHBoxLayout()
        user_repo_layout.setSpacing(12)
        
        # 用户名
        user_container = QVBoxLayout()
        user_container.setSpacing(4)
        self.userLabel = BodyLabel("用户名: *", self)
        self.userEdit = LineEdit(self)
        self.userEdit.setPlaceholderText("如: username")
        self.userEdit.setClearButtonEnabled(True)
        user_container.addWidget(self.userLabel)
        user_container.addWidget(self.userEdit)
        user_repo_layout.addLayout(user_container, 1)
        
        # 仓库名
        repo_container = QVBoxLayout()
        repo_container.setSpacing(4)
        self.repoLabel = BodyLabel("仓库名: *", self)
        from qfluentwidgetspro import LabelLineEdit
        self.repoEdit = LabelLineEdit(self)
        self.repoEdit.setPlaceholderText("如: repository")
        self.repoEdit.setSuffix(".git")
        self.repoEdit.setClearButtonEnabled(True)
        repo_container.addWidget(self.repoLabel)
        repo_container.addWidget(self.repoEdit)
        user_repo_layout.addLayout(repo_container, 1)
        
        layout.addLayout(user_repo_layout)
        
        layout.addSpacing(8)
        
        # URL预览（紧凑显示）
        self.urlPreviewLabel = BodyLabel("", self)
        self.urlPreviewLabel.setTextColor(QColor(0, 120, 212), QColor(0, 153, 255))
        self.urlPreviewLabel.setWordWrap(True)
        layout.addWidget(self.urlPreviewLabel)
        
        layout.addStretch()
        
        # 所有UI元素创建完成后，再连接信号
        self.hostEdit.textChanged.connect(self._update_url_preview)
        self.userEdit.textChanged.connect(self._update_url_preview)
        self.repoEdit.textChanged.connect(self._update_url_preview)
        self.sshPortEdit.textChanged.connect(self._update_url_preview)
        
        # 初始更新预览
        self._update_url_preview()
    
    def _on_protocol_changed(self, protocol: str):
        """协议类型变化时的处理"""
        # 显示/隐藏SSH端口
        if protocol == "git":
            self.sshPortLabel.show()
            self.sshPortEdit.show()
        else:
            self.sshPortLabel.hide()
            self.sshPortEdit.hide()
        
        # 更新URL预览
        self._update_url_preview()
    
    def _update_url_preview(self):
        """更新URL预览"""
        protocol = self.protocolSegmented.currentItem()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        port = self.sshPortEdit.text().strip() or "22"
        
        if not host or not user or not repo:
            self.urlPreviewLabel.setText("📋 预览: 请填写完整信息")
            self.urlPreviewLabel.setTextColor(QColor(150, 150, 150), QColor(150, 150, 150))
            return
        
        # 组合路径（repoEdit只包含仓库名，需要添加.git后缀）
        repo_with_suffix = f"{repo}.git" if repo and not repo.endswith('.git') else repo
        path = f"{user}/{repo_with_suffix}"
        
        # 根据协议类型组合URL
        if protocol == "https":
            url = f"https://{host}/{path}"
        else:  # git (SSH)
            if port != "22":
                url = f"ssh://git@{host}:{port}/{path}"
            else:
                url = f"git@{host}:{path}"
        
        self.urlPreviewLabel.setText(f"📋 {url}")
        self.urlPreviewLabel.setTextColor(QColor(0, 120, 212), QColor(0, 153, 255))
    
    def _validate_inputs(self):
        """验证输入是否完整"""
        name = self.nameEdit.text().strip()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        
        return bool(name and host and user and repo)
    
    def get_remote_info(self) -> tuple[str, str]:
        """获取远程仓库信息（自动组合URL）"""
        name = self.nameEdit.text().strip()
        protocol = self.protocolSegmented.currentItem()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        port = self.sshPortEdit.text().strip() or "22"
        
        # 组合路径（repoEdit只包含仓库名，需要添加.git后缀）
        repo_with_suffix = f"{repo}.git" if repo and not repo.endswith('.git') else repo
        path = f"{user}/{repo_with_suffix}"
        
        # 根据协议类型组合URL
        if protocol == "https":
            url = f"https://{host}/{path}"
        else:  # git (SSH)
            if port != "22":
                url = f"ssh://git@{host}:{port}/{path}"
            else:
                url = f"git@{host}:{path}"
        
        return name, url
    
    def is_valid(self) -> bool:
        """验证是否可以继续下一步"""
        name = self.nameEdit.text().strip()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        return bool(name and host and user and repo)


class OptionalRemoteInterface(QWidget):
    """可选的远程仓库配置界面 - 用于初始化仓库向导"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("添加远程仓库", self)
        setFont(self.titleLabel, 24, QFont.Weight.Bold)
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
        
        layout.addSpacing(12)
        
        # 远程名称
        self.nameLabel = BodyLabel("远程名称:", self)
        layout.addWidget(self.nameLabel)
        
        self.nameEdit = LineEdit(self)
        self.nameEdit.setText("origin")
        self.nameEdit.setPlaceholderText("通常使用 origin")
        layout.addWidget(self.nameEdit)
        
        layout.addSpacing(8)
        
        # 协议选择
        from qfluentwidgets import SegmentedWidget
        self.protocolLabel = BodyLabel("协议类型:", self)
        layout.addWidget(self.protocolLabel)
        
        self.protocolSegmented = SegmentedWidget(self)
        self.protocolSegmented.addItem("https", "HTTPS", lambda: self._on_protocol_changed("https"))
        self.protocolSegmented.addItem("git", "SSH", lambda: self._on_protocol_changed("git"))
        self.protocolSegmented.setCurrentItem("https")
        layout.addWidget(self.protocolSegmented)
        
        layout.addSpacing(8)
        
        # 第1行：主机名 + SSH端口
        host_port_layout = QHBoxLayout()
        host_port_layout.setSpacing(12)
        
        host_container = QVBoxLayout()
        host_container.setSpacing(4)
        self.hostLabel = BodyLabel("主机名:", self)
        self.hostEdit = LineEdit(self)
        self.hostEdit.setPlaceholderText("如: github.com")
        self.hostEdit.setClearButtonEnabled(True)
        host_container.addWidget(self.hostLabel)
        host_container.addWidget(self.hostEdit)
        host_port_layout.addLayout(host_container, 3)
        
        port_container = QVBoxLayout()
        port_container.setSpacing(4)
        self.sshPortLabel = BodyLabel("SSH端口:", self)
        self.sshPortEdit = LineEdit(self)
        self.sshPortEdit.setText("22")
        self.sshPortEdit.setPlaceholderText("默认: 22")
        self.sshPortEdit.setClearButtonEnabled(True)
        port_container.addWidget(self.sshPortLabel)
        port_container.addWidget(self.sshPortEdit)
        host_port_layout.addLayout(port_container, 1)
        
        layout.addLayout(host_port_layout)
        
        # 初始隐藏SSH端口
        self.sshPortLabel.hide()
        self.sshPortEdit.hide()
        
        layout.addSpacing(8)
        
        # 第2行：用户名 + 仓库名
        user_repo_layout = QHBoxLayout()
        user_repo_layout.setSpacing(12)
        
        user_container = QVBoxLayout()
        user_container.setSpacing(4)
        self.userLabel = BodyLabel("用户名:", self)
        self.userEdit = LineEdit(self)
        self.userEdit.setPlaceholderText("如: username")
        self.userEdit.setClearButtonEnabled(True)
        user_container.addWidget(self.userLabel)
        user_container.addWidget(self.userEdit)
        user_repo_layout.addLayout(user_container, 1)
        
        repo_container = QVBoxLayout()
        repo_container.setSpacing(4)
        self.repoLabel = BodyLabel("仓库名:", self)
        from qfluentwidgetspro import LabelLineEdit
        self.repoEdit = LabelLineEdit(self)
        self.repoEdit.setPlaceholderText("如: repository")
        self.repoEdit.setSuffix(".git")
        self.repoEdit.setClearButtonEnabled(True)
        repo_container.addWidget(self.repoLabel)
        repo_container.addWidget(self.repoEdit)
        user_repo_layout.addLayout(repo_container, 1)
        
        layout.addLayout(user_repo_layout)
        
        layout.addSpacing(8)
        
        # URL预览
        self.urlPreviewLabel = BodyLabel("", self)
        self.urlPreviewLabel.setTextColor(QColor(0, 120, 212), QColor(0, 153, 255))
        self.urlPreviewLabel.setWordWrap(True)
        layout.addWidget(self.urlPreviewLabel)
        
        layout.addStretch()
        
        # 连接信号
        self.hostEdit.textChanged.connect(self._update_url_preview)
        self.userEdit.textChanged.connect(self._update_url_preview)
        self.repoEdit.textChanged.connect(self._update_url_preview)
        self.sshPortEdit.textChanged.connect(self._update_url_preview)
        
        # 初始更新预览
        self._update_url_preview()
    
    def _on_protocol_changed(self, protocol: str):
        """协议类型变化时的处理"""
        if protocol == "git":
            self.sshPortLabel.show()
            self.sshPortEdit.show()
        else:
            self.sshPortLabel.hide()
            self.sshPortEdit.hide()
        
        self._update_url_preview()
    
    def _update_url_preview(self):
        """更新URL预览"""
        protocol = self.protocolSegmented.currentItem()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        port = self.sshPortEdit.text().strip() or "22"
        
        if not host or not user or not repo:
            self.urlPreviewLabel.setText("📋 预览: 请填写完整信息")
            self.urlPreviewLabel.setTextColor(QColor(150, 150, 150), QColor(150, 150, 150))
            return
        
        # 组合路径（repoEdit只包含仓库名，需要添加.git后缀）
        repo_with_suffix = f"{repo}.git" if repo and not repo.endswith('.git') else repo
        path = f"{user}/{repo_with_suffix}"
        
        # 根据协议类型组合URL
        if protocol == "https":
            url = f"https://{host}/{path}"
        else:  # git (SSH)
            if port != "22":
                url = f"ssh://git@{host}:{port}/{path}"
            else:
                url = f"git@{host}:{path}"
        
        self.urlPreviewLabel.setText(f"📋 {url}")
        self.urlPreviewLabel.setTextColor(QColor(0, 120, 212), QColor(0, 153, 255))
    
    def get_remote_info(self) -> tuple[str, str]:
        """获取远程仓库信息（自动组合URL）"""
        name = self.nameEdit.text().strip()
        protocol = self.protocolSegmented.currentItem()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        port = self.sshPortEdit.text().strip() or "22"
        
        # 组合路径（repoEdit只包含仓库名，需要添加.git后缀）
        repo_with_suffix = f"{repo}.git" if repo and not repo.endswith('.git') else repo
        path = f"{user}/{repo_with_suffix}"
        
        # 根据协议类型组合URL
        if protocol == "https":
            url = f"https://{host}/{path}"
        else:  # git (SSH)
            if port != "22":
                url = f"ssh://git@{host}:{port}/{path}"
            else:
                url = f"git@{host}:{path}"
        
        return name, url


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
