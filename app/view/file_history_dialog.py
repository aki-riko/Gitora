# coding:utf-8
"""
文件历史对话框
显示文件的提交历史，支持查看不同版本和对比
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QTextEdit, QWidget

from qfluentwidgets import (
    Dialog, PushButton, TransparentPushButton, FluentIcon,
    InfoBar, InfoBarPosition, BodyLabel, CaptionLabel,
    StrongBodyLabel, CardWidget, ScrollArea
)
from qfluentwidgetspro import TimeLineWidget, TimeLineCard, InfoBarIcon

from ..common.git_service import gitService, CommitInfo
from ..common.logger import get_logger

logger = get_logger("FileHistoryDialog")


class FileCommitCard(TimeLineCard):
    """文件提交卡片"""
    
    def __init__(self, commit: CommitInfo, parent=None):
        text = f"{commit.message}\n{commit.author} · {commit.short_hash} · {commit.date}"
        super().__init__(text, parent, InfoBarIcon.SUCCESS)
        self.commit = commit


class FileHistoryDialog(Dialog):
    """文件历史对话框"""
    
    def __init__(self, file_path: str, parent=None):
        super().__init__(self.tr("文件历史"), self.tr("查看 %s 的提交历史") % file_path, parent)
        self.file_path = file_path
        self.commits = []
        self._setup_ui()
        self._load_history()
    
    def _setup_ui(self):
        # 设置对话框大小
        self.setFixedSize(900, 600)
        
        # 说明
        hint_label = BodyLabel(
            self.tr("点击提交记录查看该版本的文件内容，选择两个版本可以进行对比"),
            self
        )
        self.textLayout.addWidget(hint_label)
        
        # 主内容区（左右分割）
        content_layout = QHBoxLayout()
        
        # 左侧：提交历史时间线
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        timeline_label = StrongBodyLabel(self.tr("提交历史"), self)
        left_layout.addWidget(timeline_label)
        
        # 时间线滚动区域
        timeline_scroll = ScrollArea()
        timeline_scroll.setWidgetResizable(True)
        timeline_scroll.setFixedWidth(350)
        
        timeline_container = QWidget()
        timeline_layout = QVBoxLayout(timeline_container)
        timeline_layout.setContentsMargins(0, 0, 0, 0)
        
        self.timeLine = TimeLineWidget(timeline_container)
        timeline_layout.addWidget(self.timeLine)
        
        timeline_scroll.setWidget(timeline_container)
        left_layout.addWidget(timeline_scroll)
        
        content_layout.addWidget(left_widget)
        
        # 右侧：文件内容显示
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.viewBtn = TransparentPushButton(self.tr("查看此版本"), self, FluentIcon.VIEW)
        self.viewBtn.clicked.connect(self._on_view_version)
        self.viewBtn.setEnabled(False)
        btn_layout.addWidget(self.viewBtn)
        
        self.compareBtn = PushButton(self.tr("对比两个版本"), self, FluentIcon.ALIGNMENT)
        self.compareBtn.clicked.connect(self._on_compare_versions)
        self.compareBtn.setEnabled(False)
        btn_layout.addWidget(self.compareBtn)
        
        btn_layout.addStretch()
        right_layout.addLayout(btn_layout)
        
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
            }
        """)
        self.contentEdit.setPlaceholderText(self.tr("选择一个提交查看文件内容"))
        right_layout.addWidget(self.contentEdit)
        
        content_layout.addWidget(right_widget, 1)
        
        self.textLayout.addLayout(content_layout)
        
        # 修改按钮文本
        self.yesButton.setText(self.tr("关闭"))
        self.cancelButton.hide()
        
        # 选中的提交
        self.selected_commits = []
    
    def _load_history(self):
        """加载文件历史（异步）"""
        def on_load_finished(commits):
            self.commits = commits
            
            if not commits:
                self.timeLine.addItem(InfoBarIcon.INFORMATION, self.tr("此文件没有提交历史"))
                return
            
            for commit in commits:
                card = FileCommitCard(commit, self.timeLine)
                card.clicked.connect(lambda checked=False, c=commit: self._on_commit_selected(c))
                self.timeLine.addItem(
                    InfoBarIcon.SUCCESS,
                    commit.date.split(' ')[0],
                    [card]
                )
        
        # 使用封装的异步工具
        from app.common.async_helper import SimpleAsyncTask
        
        SimpleAsyncTask.run(
            lambda: gitService.get_file_history(self.file_path, count=50),
            on_load_finished
        )
    
    def _on_commit_selected(self, commit: CommitInfo):
        """选中提交"""
        # 切换选中状态
        if commit in self.selected_commits:
            self.selected_commits.remove(commit)
        else:
            self.selected_commits.append(commit)
            # 最多选择2个
            if len(self.selected_commits) > 2:
                self.selected_commits.pop(0)
        
        # 更新按钮状态
        self.viewBtn.setEnabled(len(self.selected_commits) >= 1)
        self.compareBtn.setEnabled(len(self.selected_commits) == 2)
        
        # 如果只选中1个，显示该版本内容
        if len(self.selected_commits) == 1:
            self._view_single_version(self.selected_commits[0])
    
    def _view_single_version(self, commit: CommitInfo):
        """查看单个版本"""
        content = gitService.get_file_content_at_commit(self.file_path, commit.hash)
        self.contentEdit.setPlainText(content)
    
    def _on_view_version(self):
        """查看选中版本"""
        if self.selected_commits:
            self._view_single_version(self.selected_commits[-1])
    
    def _on_compare_versions(self):
        """对比两个版本"""
        if len(self.selected_commits) != 2:
            return
        
        commit1, commit2 = self.selected_commits
        # 确保commit1是较旧的版本
        if self.commits.index(commit1) > self.commits.index(commit2):
            commit1, commit2 = commit2, commit1
        
        diff = gitService.diff_file_between_commits(
            self.file_path,
            commit1.hash,
            commit2.hash
        )
        
        if diff:
            self.contentEdit.setPlainText(
                f"对比: {commit1.short_hash} → {commit2.short_hash}\n"
                f"{commit1.date} → {commit2.date}\n\n"
                f"{diff}"
            )
        else:
            self.contentEdit.setPlainText(self.tr("两个版本之间没有差异"))
