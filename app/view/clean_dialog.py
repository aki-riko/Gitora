# coding:utf-8
"""
清理未跟踪文件对话框
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import (
    Dialog, BodyLabel, CheckBox, ScrollArea,
    InfoBar, InfoBarPosition, MessageBox
)

from ..common.git_service import gitService


class CleanDialog(Dialog):
    """清理未跟踪文件对话框"""
    
    def __init__(self, parent=None):
        super().__init__(
            title="清理未跟踪文件",
            content="删除所有未被Git跟踪的文件和目录",
            parent=parent
        )
        self._setup_content()
        self._preview_files()
    
    def _setup_content(self):
        self.setFixedSize(600, 500)
        
        # 警告
        warning = BodyLabel("⚠️ 警告：此操作不可恢复！", self)
        self.textLayout.addWidget(warning)
        
        # 选项
        self.includeDirCheckbox = CheckBox("包括目录", self)
        self.includeDirCheckbox.setChecked(True)
        self.textLayout.addWidget(self.includeDirCheckbox)
        
        # 文件列表
        list_label = BodyLabel("将被删除的文件：", self)
        self.textLayout.addWidget(list_label)
        
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(300)
        
        self.fileListWidget = QWidget()
        self.fileListLayout = QVBoxLayout(self.fileListWidget)
        self.fileListLayout.setContentsMargins(0, 0, 0, 0)
        self.fileListLayout.setSpacing(4)
        
        scroll.setWidget(self.fileListWidget)
        self.textLayout.addWidget(scroll)
        
        # 按钮
        self.yesButton.setText("确认清理")
        self.cancelButton.setText("取消")
    
    def _preview_files(self):
        """预览将被清理的文件"""
        files = gitService.clean_preview()
        
        if not files:
            label = BodyLabel("没有需要清理的文件", self)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fileListLayout.addWidget(label)
            self.yesButton.setEnabled(False)
        else:
            for file in files:
                label = BodyLabel(f"• {file}", self)
                self.fileListLayout.addWidget(label)
