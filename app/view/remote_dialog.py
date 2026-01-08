# coding:utf-8
"""
远程仓库配置对话框
"""
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout
from PySide6.QtGui import QColor
from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, LineEdit, BodyLabel, InfoBar, InfoBarPosition
)

from ..common.git_service import gitService
from ..common.logger import get_logger

logger = get_logger("RemoteDialog")


class RemoteDialog(MessageBoxBase):
    """远程仓库配置对话框"""
    
    def __init__(self, parent=None, is_new_repo=False):
        super().__init__(parent)
        self.is_new_repo = is_new_repo
        self._setup_content()
    
    def _setup_content(self):
        # 标题
        title = self.tr("添加远程仓库") if self.is_new_repo else self.tr("配置远程仓库")
        self.titleLabel = SubtitleLabel(title, self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # 描述
        content = self.tr("请输入远程仓库信息（可选，稍后也可以配置）") if self.is_new_repo else self.tr("请输入远程仓库信息")
        self.descLabel = BodyLabel(content, self)
        self.viewLayout.addWidget(self.descLabel)
        
        # 设置最小宽度
        self.widget.setMinimumWidth(500)
        
        # 远程仓库名称
        name_layout = QHBoxLayout()
        name_label = BodyLabel(self.tr("远程名称:"), self)
        name_label.setFixedWidth(80)
        self.nameEdit = LineEdit(self)
        self.nameEdit.setText("origin")
        self.nameEdit.setPlaceholderText(self.tr("通常使用 origin"))
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.nameEdit)
        self.viewLayout.addLayout(name_layout)
        
        # 协议选择
        from qfluentwidgets import SegmentedWidget
        protocol_layout = QHBoxLayout()
        protocol_label = BodyLabel(self.tr("协议类型:"), self)
        protocol_label.setFixedWidth(80)
        self.protocolSegmented = SegmentedWidget(self)
        self.protocolSegmented.addItem("https", "HTTPS", lambda: self._on_protocol_changed("https"))
        self.protocolSegmented.addItem("git", "SSH", lambda: self._on_protocol_changed("git"))
        self.protocolSegmented.setCurrentItem("https")
        protocol_layout.addWidget(protocol_label)
        protocol_layout.addWidget(self.protocolSegmented)
        self.viewLayout.addLayout(protocol_layout)
        
        # 第1行：主机名 + SSH端口
        host_port_layout = QHBoxLayout()
        host_port_layout.setSpacing(8)
        
        host_label = BodyLabel(self.tr("主机名:"), self)
        host_label.setFixedWidth(80)
        self.hostEdit = LineEdit(self)
        self.hostEdit.setPlaceholderText("如: github.com")
        self.hostEdit.setClearButtonEnabled(True)
        self.hostEdit.textChanged.connect(self._update_url_preview)
        host_port_layout.addWidget(host_label)
        host_port_layout.addWidget(self.hostEdit, 3)
        
        self.port_label = BodyLabel(self.tr("SSH端口:"), self)
        self.port_label.setFixedWidth(70)
        self.sshPortEdit = LineEdit(self)
        self.sshPortEdit.setText("22")
        self.sshPortEdit.setPlaceholderText("22")
        self.sshPortEdit.setClearButtonEnabled(True)
        self.sshPortEdit.textChanged.connect(self._update_url_preview)
        host_port_layout.addWidget(self.port_label)
        host_port_layout.addWidget(self.sshPortEdit, 1)
        
        self.viewLayout.addLayout(host_port_layout)
        
        # 初始隐藏SSH端口
        self.port_label.hide()
        self.sshPortEdit.hide()
        
        # 第2行：用户名 + 仓库名
        user_repo_layout = QHBoxLayout()
        user_repo_layout.setSpacing(8)
        
        user_label = BodyLabel(self.tr("用户名:"), self)
        user_label.setFixedWidth(80)
        self.userEdit = LineEdit(self)
        self.userEdit.setPlaceholderText("如: username")
        self.userEdit.setClearButtonEnabled(True)
        self.userEdit.textChanged.connect(self._update_url_preview)
        user_repo_layout.addWidget(user_label)
        user_repo_layout.addWidget(self.userEdit, 1)
        
        repo_label = BodyLabel(self.tr("仓库名:"), self)
        repo_label.setFixedWidth(70)
        from qfluentwidgetspro import LabelLineEdit
        self.repoEdit = LabelLineEdit(self)
        self.repoEdit.setPlaceholderText("如: repo")
        self.repoEdit.setSuffix(".git")
        self.repoEdit.setClearButtonEnabled(True)
        self.repoEdit.textChanged.connect(self._update_url_preview)
        user_repo_layout.addWidget(repo_label)
        user_repo_layout.addWidget(self.repoEdit, 1)
        
        self.viewLayout.addLayout(user_repo_layout)
        
        # URL预览
        preview_layout = QHBoxLayout()
        preview_label = BodyLabel("📋 URL:", self)
        preview_label.setFixedWidth(80)
        self.urlPreviewLabel = BodyLabel("", self)
        self.urlPreviewLabel.setTextColor(QColor(0, 120, 212), QColor(0, 153, 255))
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(self.urlPreviewLabel)
        self.viewLayout.addLayout(preview_layout)
        
        if self.is_new_repo:
            skip_hint_label = BodyLabel(self.tr("💡 提示：如果暂时不配置，可以点击取消，稍后在设置中添加"), self)
            skip_hint_label.setWordWrap(True)
            self.viewLayout.addWidget(skip_hint_label)
        
        # 初始更新预览
        self._update_url_preview()
        
        # 修改按钮文本
        self.yesButton.setText(self.tr("添加"))
        self.cancelButton.setText(self.tr("跳过") if self.is_new_repo else self.tr("取消"))
    
    def _on_protocol_changed(self, protocol: str):
        """协议类型变化时的处理"""
        if protocol == "git":
            self.port_label.show()
            self.sshPortEdit.show()
        else:
            self.port_label.hide()
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
            self.urlPreviewLabel.setText(self.tr("请填写完整信息"))
            return
        
        # 组合路径（repoEdit只包含仓库名，需要添加.git后缀）
        repo_with_suffix = f"{repo}.git" if repo and not repo.endswith('.git') else repo
        path = f"{user}/{repo_with_suffix}"
        
        # 组合URL
        if protocol == "https":
            url = f"https://{host}/{path}"
        else:  # git (SSH)
            if port != "22":
                url = f"ssh://git@{host}:{port}/{path}"
            else:
                url = f"git@{host}:{path}"
        
        self.urlPreviewLabel.setText(url)
    
    def get_remote_info(self) -> tuple[str, str]:
        """获取远程仓库信息 (name, url)"""
        name = self.nameEdit.text().strip()
        protocol = self.protocolSegmented.currentItem()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        port = self.sshPortEdit.text().strip() or "22"
        
        # 组合路径（repoEdit只包含仓库名，需要添加.git后缀）
        repo_with_suffix = f"{repo}.git" if repo and not repo.endswith('.git') else repo
        path = f"{user}/{repo_with_suffix}"
        
        # 组合URL
        if protocol == "https":
            url = f"https://{host}/{path}"
        else:  # git (SSH)
            if port != "22":
                url = f"ssh://git@{host}:{port}/{path}"
            else:
                url = f"git@{host}:{path}"
        
        return name, url
    
    def validate(self) -> bool:
        """验证输入"""
        name = self.nameEdit.text().strip()
        host = self.hostEdit.text().strip()
        user = self.userEdit.text().strip()
        repo = self.repoEdit.text().strip()
        
        if not name:
            InfoBar.warning(
                self.tr("提示"),
                self.tr("请输入远程仓库名称"),
                parent=self.window(),
                position=InfoBarPosition.BOTTOM,
                duration=2000
            )
            return False
        
        if not host:
            InfoBar.warning(
                self.tr("提示"),
                self.tr("请输入主机名"),
                parent=self.window(),
                position=InfoBarPosition.BOTTOM,
                duration=2000
            )
            return False
        
        if not user:
            InfoBar.warning(
                self.tr("提示"),
                self.tr("请输入用户名"),
                parent=self.window(),
                position=InfoBarPosition.BOTTOM,
                duration=2000
            )
            return False
        
        if not repo:
            InfoBar.warning(
                self.tr("提示"),
                self.tr("请输入仓库名"),
                parent=self.window(),
                position=InfoBarPosition.BOTTOM,
                duration=2000
            )
            return False
        
        return True
