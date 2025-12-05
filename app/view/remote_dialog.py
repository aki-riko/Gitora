# coding:utf-8
"""
远程仓库配置对话框
"""
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    Dialog, LineEdit, BodyLabel, InfoBar, InfoBarPosition
)

from ..common.git_service import gitService


class RemoteDialog(Dialog):
    """远程仓库配置对话框"""
    
    def __init__(self, parent=None, is_new_repo=False):
        title = "添加远程仓库" if is_new_repo else "配置远程仓库"
        content = "请输入远程仓库信息（可选，稍后也可以配置）" if is_new_repo else "请输入远程仓库信息"
        super().__init__(title, content, parent)
        self.is_new_repo = is_new_repo
        self._setup_content()
    
    def _setup_content(self):
        # 远程仓库名称
        name_layout = QHBoxLayout()
        name_label = BodyLabel("远程名称:", self)
        name_label.setFixedWidth(80)
        self.nameEdit = LineEdit(self)
        self.nameEdit.setText("origin")
        self.nameEdit.setPlaceholderText("通常使用 origin")
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.nameEdit)
        self.textLayout.addLayout(name_layout)
        
        # 远程仓库URL
        url_layout = QHBoxLayout()
        url_label = BodyLabel("远程URL:", self)
        url_label.setFixedWidth(80)
        self.urlEdit = LineEdit(self)
        self.urlEdit.setPlaceholderText("如: https://github.com/user/repo.git")
        self.urlEdit.setClearButtonEnabled(True)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.urlEdit)
        self.textLayout.addLayout(url_layout)
        
        # 提示信息
        if self.is_new_repo:
            hint_label = BodyLabel("💡 提示：如果暂时不配置，可以点击取消，稍后在设置中添加", self)
            hint_label.setWordWrap(True)
            self.textLayout.addWidget(hint_label)
        
        # 修改按钮文本
        self.yesButton.setText("添加")
        self.cancelButton.setText("跳过" if self.is_new_repo else "取消")
    
    def get_remote_info(self) -> tuple[str, str]:
        """获取远程仓库信息 (name, url)"""
        return self.nameEdit.text().strip(), self.urlEdit.text().strip()
    
    def validate(self) -> bool:
        """验证输入"""
        name = self.nameEdit.text().strip()
        url = self.urlEdit.text().strip()
        
        if not name:
            InfoBar.warning(
                "提示",
                "请输入远程仓库名称",
                parent=self.window(),
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=2000
            )
            return False
        
        if not url:
            InfoBar.warning(
                "提示",
                "请输入远程仓库URL",
                parent=self.window(),
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=2000
            )
            return False
        
        return True
