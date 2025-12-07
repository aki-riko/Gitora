# coding:utf-8
"""
克隆仓库对话框
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QFileDialog

from qfluentwidgets import (
    Dialog, LineEdit, PushButton, TransparentPushButton,
    FluentIcon, InfoBar, InfoBarPosition, BodyLabel
)

from ..common.git_service import gitService
from ..common.logger import get_logger

logger = get_logger("CloneDialog")


class CloneDialog(Dialog):
    """克隆仓库对话框"""
    
    def __init__(self, parent=None):
        super().__init__(
            title=self.tr("克隆Git仓库"),
            content=self.tr("从远程URL克隆仓库到本地"),
            parent=parent
        )
        self._setup_content()
    
    def _setup_content(self):
        # URL输入
        url_label = BodyLabel(self.tr("仓库URL:"), self)
        self.textLayout.addWidget(url_label)
        
        self.urlEdit = LineEdit(self)
        self.urlEdit.setPlaceholderText("https://github.com/username/repo.git")
        self.urlEdit.setClearButtonEnabled(True)
        self.textLayout.addWidget(self.urlEdit)
        
        # 本地路径
        path_label = BodyLabel(self.tr("本地路径:"), self)
        self.textLayout.addWidget(path_label)
        
        path_layout = QVBoxLayout()
        
        self.pathEdit = LineEdit(self)
        self.pathEdit.setPlaceholderText(self.tr("选择克隆到的本地目录"))
        self.pathEdit.setClearButtonEnabled(True)
        path_layout.addWidget(self.pathEdit)
        
        browse_btn = TransparentPushButton(self.tr("浏览..."), self, FluentIcon.FOLDER)
        browse_btn.clicked.connect(self._browse_path)
        path_layout.addWidget(browse_btn)
        
        self.textLayout.addLayout(path_layout)
        
        # 修改按钮文字
        self.yesButton.setText(self.tr("开始克隆"))
        self.cancelButton.setText(self.tr("取消"))
    
    def _browse_path(self):
        """浏览本地路径"""
        path = QFileDialog.getExistingDirectory(
            self,
            self.tr("选择克隆目录"),
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if path:
            self.pathEdit.setText(path)
    
    def get_clone_info(self) -> tuple[str, str]:
        """获取克隆信息 (url, path)"""
        return self.urlEdit.text().strip(), self.pathEdit.text().strip()
