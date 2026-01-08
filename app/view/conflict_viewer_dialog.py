# coding:utf-8
"""
冲突内容查看对话框
显示包含冲突标记的文件内容
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QTextEdit
from PySide6.QtGui import QColor

from qfluentwidgets import MessageBoxBase, SubtitleLabel, BodyLabel

from ..common.logger import get_logger

logger = get_logger("ConflictViewerDialog")


class ConflictViewerDialog(MessageBoxBase):
    """冲突内容查看对话框"""
    
    def __init__(self, file_path: str, content: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.content = content
        self._setup_ui()
    
    def _setup_ui(self):
        # 标题
        self.titleLabel = SubtitleLabel(self.tr("查看冲突内容"), self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # 设置最小宽度
        self.widget.setMinimumWidth(750)
        
        # 文件路径标签
        path_label = BodyLabel(self.tr("文件: ") + self.file_path, self)
        self.viewLayout.addWidget(path_label)
        
        # 说明标签
        hint_label = BodyLabel(
            self.tr("<<<<<<< HEAD 和 ======= 之间是我们的版本") + "\n" +
            self.tr("======= 和 >>>>>>> 之间是他们的版本"),
            self
        )
        self.viewLayout.addWidget(hint_label)
        
        # 内容显示区域
        self.contentEdit = QTextEdit(self)
        self.contentEdit.setReadOnly(True)
        self.contentEdit.setStyleSheet("""
            QTextEdit {
                background-color: rgba(0, 0, 0, 0.05);
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                line-height: 1.5;
            }
        """)
        self.contentEdit.setFixedHeight(400)
        self.viewLayout.addWidget(self.contentEdit)
        
        # 格式化显示内容（高亮冲突标记）
        self._format_content()
        
        # 只显示关闭按钮
        self.cancelButton.setText(self.tr("关闭"))
        self.yesButton.hide()
    
    def _format_content(self):
        """格式化并高亮冲突标记"""
        from qfluentwidgets import isDarkTheme
        self.contentEdit.clear()
        
        # 主题感知颜色
        is_dark = isDarkTheme()
        default_color = QColor(255, 255, 255) if is_dark else QColor(0, 0, 0)
        
        lines = self.content.split('\n')
        for line in lines:
            if line.startswith('<<<<<<<'):
                # 我们的版本标记 - 蓝色
                self.contentEdit.setTextColor(QColor(66, 165, 245) if is_dark else QColor(33, 150, 243))
                self.contentEdit.append(line)
            elif line.startswith('======='):
                # 分隔符 - 橙色
                self.contentEdit.setTextColor(QColor(255, 152, 0))
                self.contentEdit.append(line)
            elif line.startswith('>>>>>>>'):
                # 他们的版本标记 - 绿色
                self.contentEdit.setTextColor(QColor(76, 175, 80))
                self.contentEdit.append(line)
            else:
                # 普通行 - 主题感知颜色
                self.contentEdit.setTextColor(default_color)
                self.contentEdit.append(line)
