# coding:utf-8
"""
Reflog引用日志对话框
用于查看和恢复丢失的提交
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget

from qfluentwidgets import (
    Dialog, BodyLabel, CaptionLabel, StrongBodyLabel, CardWidget,
    PushButton, TransparentPushButton, FluentIcon, InfoBar, InfoBarPosition,
    MessageBox, ScrollArea
)

from ..common.git_service import gitService
from ..common.icon import Icon
from ..common.logger import get_logger

logger = get_logger("ReflogDialog")


class ReflogCard(CardWidget):
    """Reflog条目卡片"""
    
    def __init__(self, hash_val: str, ref: str, message: str, parent=None):
        super().__init__(parent)
        self.hash_val = hash_val
        self.ref = ref
        self.message = message
        self._setup_ui()
    
    def _setup_ui(self):
        self.setFixedHeight(64)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        # 引用和消息
        msg_label = StrongBodyLabel(f"{self.ref}: {self.message}", self)
        info_layout.addWidget(msg_label)
        
        # Hash
        hash_label = CaptionLabel(self.hash_val[:7], self)
        info_layout.addWidget(hash_label)
        
        layout.addLayout(info_layout, 1)
        
        # 操作按钮
        checkout_btn = TransparentPushButton("检出", self, Icon.GIT_COMMIT)
        checkout_btn.clicked.connect(self._on_checkout)
        layout.addWidget(checkout_btn)
    
    def _on_checkout(self):
        """检出此提交"""
        box = MessageBox(
            "确认检出",
            f"确定要检出到 {self.hash_val[:7]} 吗？\n这将进入分离头指针状态。",
            self.window()
        )
        if box.exec():
            from app.common.async_helper import AsyncTask
            
            commit_hash = self.hash_val[:7]
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success("成功", msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
                else:
                    InfoBar.error("失败", msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
            
            AsyncTask.run(
                func=lambda: gitService.checkout_branch(commit_hash),
                on_success=on_success,
                progress_title='请稍候',
                progress_content=f'正在检出到 {commit_hash}...',
                parent=self.window()
            )


class ReflogDialog(Dialog):
    """Reflog引用日志对话框"""
    
    def __init__(self, parent=None):
        super().__init__("引用日志 (Reflog)", "查看所有引用变更记录，可恢复丢失的提交", parent)
        self._setup_ui()
        self._load_reflog()
    
    def _setup_ui(self):
        self.setFixedSize(800, 600)
        
        # 说明
        hint = BodyLabel("引用日志 (Reflog) 记录了所有引用的变更历史，即使提交被删除也能找回", self)
        self.textLayout.addWidget(hint)
        
        # 滚动区域
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(450)
        
        self.reflogWidget = QWidget()
        self.reflogLayout = QVBoxLayout(self.reflogWidget)
        self.reflogLayout.setContentsMargins(0, 0, 0, 0)
        self.reflogLayout.setSpacing(8)
        self.reflogLayout.addStretch()
        
        scroll.setWidget(self.reflogWidget)
        self.textLayout.addWidget(scroll)
        
        # 按钮
        self.yesButton.setText("关闭")
        self.cancelButton.hide()
    
    def _load_reflog(self):
        """加载reflog"""
        logs = gitService.get_reflog(count=100)
        
        if not logs:
            empty_label = BodyLabel("暂无引用日志", self)
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.reflogLayout.insertWidget(0, empty_label)
            return
        
        # 添加reflog卡片
        for hash_val, ref, message in logs:
            card = ReflogCard(hash_val, ref, message, self.reflogWidget)
            self.reflogLayout.insertWidget(
                self.reflogLayout.count() - 1,
                card
            )
