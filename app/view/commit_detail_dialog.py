# coding:utf-8
"""
提交详情对话框
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QTextEdit, QWidget
from PySide6.QtGui import QColor

from qfluentwidgets import (
    Dialog, BodyLabel, CaptionLabel, StrongBodyLabel, CardWidget,
    ScrollArea, FluentIcon, IconWidget
)

from ..common.git_service import gitService
from ..common.logger import get_logger

logger = get_logger("CommitDetailDialog")


class CommitDetailDialog(Dialog):
    """提交详情对话框"""
    
    def __init__(self, commit_hash: str, parent=None):
        super().__init__(
            title=self.tr("提交详情"),
            content="",
            parent=parent
        )
        self.commit_hash = commit_hash
        self.setFixedSize(900, 700)
        self._setup_content()
        self._load_commit_detail()
    
    def _setup_content(self):
        # 创建滚动区域
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # 提交信息卡片
        self.infoCard = CardWidget(self)
        info_layout = QVBoxLayout(self.infoCard)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setSpacing(12)
        
        # Hash
        hash_row = QHBoxLayout()
        hash_row.addWidget(CaptionLabel(self.tr("Hash:"), self))
        self.hashLabel = BodyLabel("", self)
        self.hashLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hash_row.addWidget(self.hashLabel, 1)
        info_layout.addLayout(hash_row)
        
        # 作者
        author_row = QHBoxLayout()
        author_row.addWidget(CaptionLabel(self.tr("作者:"), self))
        self.authorLabel = BodyLabel("", self)
        author_row.addWidget(self.authorLabel, 1)
        info_layout.addLayout(author_row)
        
        # 日期
        date_row = QHBoxLayout()
        date_row.addWidget(CaptionLabel(self.tr("日期:"), self))
        self.dateLabel = BodyLabel("", self)
        date_row.addWidget(self.dateLabel, 1)
        info_layout.addLayout(date_row)
        
        # 提交信息
        self.messageLabel = StrongBodyLabel("", self)
        self.messageLabel.setWordWrap(True)
        info_layout.addWidget(self.messageLabel)
        
        layout.addWidget(self.infoCard)
        
        # 变更文件标题
        self.filesLabel = StrongBodyLabel(self.tr("变更文件"), self)
        layout.addWidget(self.filesLabel)
        
        # 文件列表
        self.filesWidget = QWidget()
        self.filesLayout = QVBoxLayout(self.filesWidget)
        self.filesLayout.setContentsMargins(0, 0, 0, 0)
        self.filesLayout.setSpacing(4)
        layout.addWidget(self.filesWidget)
        
        # Diff显示
        self.diffLabel = StrongBodyLabel(self.tr("完整Diff"), self)
        layout.addWidget(self.diffLabel)
        
        self.diffEdit = QTextEdit(self)
        self.diffEdit.setReadOnly(True)
        self.diffEdit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(0, 0, 0, 0.05);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.diffEdit)
        
        scroll.setWidget(container)
        self.textLayout.addWidget(scroll)
        
        # 设置按钮
        self.yesButton.setText(self.tr("关闭"))
        self.cancelButton.hide()
    
    def _load_commit_detail(self):
        """加载提交详情"""
        # 获取提交详情
        commit_info = gitService.get_commit_detail(self.commit_hash)
        if commit_info:
            self.hashLabel.setText(commit_info.hash)
            self.authorLabel.setText(f"{commit_info.author} <{commit_info.email}>")
            self.dateLabel.setText(commit_info.date)
            self.messageLabel.setText(commit_info.message)
        
        # 获取变更文件
        files = gitService.get_commit_files(self.commit_hash)
        if files:
            self.filesLabel.setText(self.tr("变更文件") + f" ({len(files)})")
            for file_change in files:
                file_label = BodyLabel(f"{file_change.status_text}: {file_change.path}", self)
                self.filesLayout.addWidget(file_label)
        else:
            self.filesLabel.setText(self.tr("变更文件") + " (0)")
        
        # 获取diff
        diff_text = gitService.get_commit_diff(self.commit_hash)
        if diff_text:
            self._format_diff(diff_text)
        else:
            self.diffEdit.setPlainText(self.tr("无差异"))
    
    def _format_diff(self, diff_text: str):
        """格式化diff文本"""
        from qfluentwidgets import isDarkTheme
        self.diffEdit.clear()
        
        # 主题感知颜色
        is_dark = isDarkTheme()
        default_color = QColor(255, 255, 255) if is_dark else QColor(0, 0, 0)
        
        lines = diff_text.split('\n')
        for line in lines:
            if line.startswith('+') and not line.startswith('+++'):
                self.diffEdit.setTextColor(QColor(76, 175, 80) if is_dark else QColor(34, 139, 34))
                self.diffEdit.append(line)
            elif line.startswith('-') and not line.startswith('---'):
                self.diffEdit.setTextColor(QColor(244, 67, 54) if is_dark else QColor(220, 53, 69))
                self.diffEdit.append(line)
            elif line.startswith('@@'):
                self.diffEdit.setTextColor(QColor(66, 165, 245) if is_dark else QColor(33, 150, 243))
                self.diffEdit.append(line)
            elif line.startswith('diff') or line.startswith('index') or \
                 line.startswith('---') or line.startswith('+++'):
                self.diffEdit.setTextColor(QColor(158, 158, 158))
                self.diffEdit.append(line)
            else:
                self.diffEdit.setTextColor(default_color)
                self.diffEdit.append(line)
