# coding:utf-8
"""
远程仓库配置向导
复用 RemoteInterface 组件，使用必填模式
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout

from qfluentwidgets import (
    TitleLabel, BodyLabel, setFont, ComboBox, 
    InfoBar, InfoBarPosition, TextEdit, LineEdit
)
from qfluentwidgetspro import GuideWindow

from ..common.git_service import gitService
from .init_repo_guide import RemoteInterface


class WelcomeStep(QWidget):
    """欢迎界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(28)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 标题
        self.titleLabel = TitleLabel("远程仓库配置向导", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel, 0, Qt.AlignmentFlag.AlignCenter)
        
        # 说明
        self.bodyLabel = BodyLabel(
            "检测到您的仓库远程信息不完整或需要配置。\n\n"
            "本向导将引导您完成：\n"
            "• 🌐 配置远程仓库URL\n"
            "• 🔗 设置分支跟踪关系\n"
            "• ✅ 验证远程连接\n\n"
            "⚠️ 注意：所有步骤必须完整填写才能继续",
            self
        )
        self.bodyLabel.setWordWrap(True)
        self.bodyLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.bodyLabel, 0, Qt.AlignmentFlag.AlignCenter)


class BranchConfigStep(QWidget):
    """分支配置步骤"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("配置分支跟踪", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "设置本地分支与远程分支的跟踪关系，用于推送和拉取",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        # 必填提示
        self.requiredLabel = BodyLabel(
            "⚠️ 必填项：必须选择本地分支并填写远程分支",
            self
        )
        self.requiredLabel.setWordWrap(True)
        self.requiredLabel.setTextColor(QColor(244, 67, 54), QColor(244, 67, 54))
        layout.addWidget(self.requiredLabel)
        
        layout.addSpacing(20)
        
        # 本地分支
        self.localBranchLabel = BodyLabel("本地分支: *", self)
        layout.addWidget(self.localBranchLabel)
        
        self.localBranchCombo = ComboBox(self)
        self.localBranchCombo.currentTextChanged.connect(self._validate_inputs)
        layout.addWidget(self.localBranchCombo)
        
        # 加载本地分支列表
        branches = gitService.get_branches()
        if branches:
            # 提取分支名称字符串列表
            branch_names = [b.name for b in branches if not b.is_remote]
            if branch_names:
                self.localBranchCombo.addItems(branch_names)
                current = gitService.get_current_branch()
                if current and current in branch_names:
                    self.localBranchCombo.setCurrentText(current)
        
        layout.addSpacing(12)
        
        # 远程分支
        self.remoteBranchLabel = BodyLabel("远程分支: *", self)
        layout.addWidget(self.remoteBranchLabel)
        
        # 使用LineEdit而不是ComboBox，因为QFluentWidgets的ComboBox不支持setEditable
        self.remoteBranchEdit = LineEdit(self)
        self.remoteBranchEdit.setPlaceholderText("请输入远程分支名称，如：main、master")
        self.remoteBranchEdit.setText("main")
        self.remoteBranchEdit.textChanged.connect(self._validate_inputs)
        layout.addWidget(self.remoteBranchEdit)
        
        # 提示
        self.branchHintLabel = BodyLabel(
            "💡 通常远程分支名称与本地分支相同",
            self
        )
        self.branchHintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.branchHintLabel)
        
        layout.addSpacing(12)
        
        # 验证反馈
        self.validationLabel = BodyLabel("", self)
        self.validationLabel.setWordWrap(True)
        layout.addWidget(self.validationLabel)
        
        layout.addStretch()
        
        # 初始验证
        self._validate_inputs()
    
    def _validate_inputs(self):
        """实时验证"""
        local = self.localBranchCombo.currentText().strip()
        remote = self.remoteBranchEdit.text().strip()
        
        if not local or not remote:
            self.validationLabel.setText("❌ 请选择本地分支并填写远程分支")
            self.validationLabel.setTextColor(QColor(244, 67, 54), QColor(244, 67, 54))
            return False
        else:
            self.validationLabel.setText("✅ 分支配置完整")
            self.validationLabel.setTextColor(QColor(76, 175, 80), QColor(76, 175, 80))
            return True
    
    def get_branch_config(self) -> tuple[str, str]:
        """获取分支配置"""
        return (
            self.localBranchCombo.currentText().strip(),
            self.remoteBranchEdit.text().strip()
        )
    
    def is_valid(self) -> bool:
        """验证是否有效"""
        local, remote = self.get_branch_config()
        return bool(local and remote)


class ConfirmationStep(QWidget):
    """确认配置步骤"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("确认配置", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "请确认以下配置信息，点击'完成'将执行配置",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        layout.addSpacing(20)
        
        # 配置预览
        self.configPreview = TextEdit(self)
        self.configPreview.setReadOnly(True)
        self.configPreview.setFixedHeight(200)
        layout.addWidget(self.configPreview)
        
        # 提示
        self.confirmHintLabel = BodyLabel(
            "✅ 点击'完成'将执行以下操作：\n"
            "• 添加/更新远程仓库URL\n"
            "• 设置分支跟踪关系\n"
            "• 尝试连接远程仓库验证配置\n\n"
            "⚠️ 如果远程仓库需要认证，请确保已配置SSH密钥或凭据",
            self
        )
        self.confirmHintLabel.setWordWrap(True)
        self.confirmHintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.confirmHintLabel)
        
        layout.addStretch()
    
    def set_config_preview(self, remote_name: str, remote_url: str, 
                          local_branch: str, remote_branch: str):
        """设置配置预览"""
        preview_text = (
            "远程仓库配置\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"【远程仓库】\n"
            f"名称: {remote_name}\n"
            f"URL: {remote_url}\n\n"
            f"【分支跟踪】\n"
            f"本地分支: {local_branch}\n"
            f"远程分支: {remote_name}/{remote_branch}\n\n"
            f"【Git命令等效】\n"
            f"git remote add {remote_name} {remote_url}\n"
            f"git branch --set-upstream-to={remote_name}/{remote_branch} {local_branch}"
        )
        self.configPreview.setPlainText(preview_text)


class RemoteConfigWizard(GuideWindow):
    """远程仓库配置向导（复用组件版本）"""
    
    configCompleted = Signal()  # 配置完成信号
    
    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle("远程仓库配置向导")
        self.resize(800, 500)
        
        # 获取已存在的远程列表
        self.existing_remotes = []
        remotes = gitService.get_remote_info()
        if remotes:
            self.existing_remotes = [name for name, _ in remotes]
        
        # 创建步骤页面
        self.welcomePage = WelcomeStep()
        self.remoteInfoPage = RemoteInterface(existing_remotes=self.existing_remotes)  # 始终必填
        self.branchConfigPage = BranchConfigStep()
        self.confirmationPage = ConfirmationStep()
        
        # 添加页面
        self.addPage(self.welcomePage)
        self.addPage(self.remoteInfoPage)
        self.addPage(self.branchConfigPage)
        self.addPage(self.confirmationPage)
        
        # 连接信号
        self.appStarted.connect(self._on_finish)
        self.currentIndexChanged.connect(self._on_page_changed)
    
    def _on_page_changed(self, index: int):
        """页面切换时验证"""
        # 第2页 → 第3页：验证远程信息
        if index == 2:
            if not self.remoteInfoPage.is_valid():
                InfoBar.warning(
                    "信息不完整",
                    "请填写完整的远程仓库名称和URL才能继续",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000
                )
                # 强制返回上一页
                self.setCurrentIndex(1)
                return
        
        # 第3页 → 第4页：验证分支配置并显示预览
        elif index == 3:
            if not self.branchConfigPage.is_valid():
                InfoBar.warning(
                    "信息不完整",
                    "请选择本地分支并填写远程分支名称才能继续",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000
                )
                # 强制返回上一页
                self.setCurrentIndex(2)
                return
            
            # 更新确认页预览
            remote_name, remote_url = self.remoteInfoPage.get_remote_info()
            local_branch, remote_branch = self.branchConfigPage.get_branch_config()
            self.confirmationPage.set_config_preview(
                remote_name, remote_url, local_branch, remote_branch
            )
    
    def _on_finish(self):
        """完成配置"""
        from app.common.async_helper import AsyncTask
        
        # 获取配置信息
        remote_name, remote_url = self.remoteInfoPage.get_remote_info()
        local_branch, remote_branch = self.branchConfigPage.get_branch_config()
        
        def do_config():
            """执行配置操作"""
            # 1. 添加/更新远程仓库
            if remote_name in self.existing_remotes:
                success, msg = gitService.set_remote_url(remote_name, remote_url)
                if not success:
                    raise Exception(f"更新远程URL失败: {msg}")
            else:
                success, msg = gitService.add_remote(remote_name, remote_url)
                if not success:
                    raise Exception(f"添加远程仓库失败: {msg}")
            
            # 2. 设置分支跟踪
            success, msg = gitService.set_upstream(local_branch, remote_name, remote_branch)
            if not success:
                raise Exception(f"设置分支跟踪失败: {msg}")
            
            # 3. 尝试fetch验证连接
            try:
                gitService.fetch(remote=remote_name)
            except Exception as e:
                # fetch失败不阻止配置完成，只是警告
                print(f"警告: fetch失败 - {e}")
            
            return True
        
        def on_success(result):
            """配置成功"""
            InfoBar.success(
                "配置完成",
                f"远程仓库 '{remote_name}' 已配置完成",
                parent=self.parent() if self.parent() else self,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=3000
            )
            self.configCompleted.emit()
            self.close()
        
        def on_error(e):
            """配置失败"""
            InfoBar.error(
                "配置失败",
                str(e),
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000
            )
        
        AsyncTask.run(
            func=do_config,
            on_success=on_success,
            on_error=on_error,
            progress_title='正在配置',
            progress_content='正在配置远程仓库和分支跟踪关系...',
            parent=self.parent() if self.parent() else self
        )
