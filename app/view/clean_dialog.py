# coding:utf-8
"""
清理未跟踪文件对话框
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, CheckBox, ScrollArea,
    InfoBar, InfoBarPosition, MessageBox
)

from ..common.git_service import gitService
from ..common.logger import get_logger

logger = get_logger("CleanDialog")


class CleanDialog(MessageBoxBase):
    """清理未跟踪文件对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_content()
        self._preview_files()
    
    def _setup_content(self):
        # 标题
        self.titleLabel = SubtitleLabel(self.tr("清理未跟踪文件"), self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # 描述
        self.descLabel = BodyLabel(self.tr("删除所有未被Git跟踪的文件和目录"), self)
        self.viewLayout.addWidget(self.descLabel)
        
        # 设置最小宽度
        self.widget.setMinimumWidth(550)
        
        # 警告
        warning = BodyLabel(self.tr("⚠️ 警告：此操作不可恢复！"), self)
        self.viewLayout.addWidget(warning)
        
        # 选项
        self.includeDirCheckbox = CheckBox(self.tr("包括目录"), self)
        self.includeDirCheckbox.setChecked(True)
        self.viewLayout.addWidget(self.includeDirCheckbox)
        
        # 文件列表
        list_label = BodyLabel(self.tr("将被删除的文件："), self)
        self.viewLayout.addWidget(list_label)
        
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(250)
        
        self.fileListWidget = QWidget()
        self.fileListLayout = QVBoxLayout(self.fileListWidget)
        self.fileListLayout.setContentsMargins(0, 0, 0, 0)
        self.fileListLayout.setSpacing(4)
        
        scroll.setWidget(self.fileListWidget)
        self.viewLayout.addWidget(scroll)
        
        # 按钮
        self.yesButton.setText(self.tr("确认清理"))
        self.cancelButton.setText(self.tr("取消"))
    
    def _preview_files(self):
        """预览将被清理的文件"""
        files = gitService.clean_preview()
        
        if not files:
            label = BodyLabel(self.tr("没有需要清理的文件"), self)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.fileListLayout.addWidget(label)
            self.yesButton.setEnabled(False)
        else:
            for file in files:
                label = BodyLabel(f"• {file}", self)
                self.fileListLayout.addWidget(label)
