# coding:utf-8
"""
危险操作确认对话框
带倒计时功能，防止误操作
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    MessageBoxBase, SubtitleLabel, BodyLabel, PrimaryPushButton, 
    PushButton, FluentIcon
)

from .logger import get_logger

logger = get_logger("DangerDialog")


class DangerConfirmDialog(MessageBoxBase):
    """危险操作确认对话框（带倒计时）"""
    
    def __init__(self, title: str, content: str, countdown: int = 3, parent=None):
        """
        Args:
            title: 标题
            content: 内容说明
            countdown: 倒计时秒数（默认3秒）
            parent: 父窗口
        """
        super().__init__(parent)
        self.countdown = countdown
        self._remaining = countdown
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        
        self.titleLabel = SubtitleLabel(title, self)
        self.contentLabel = BodyLabel(content, self)
        self.contentLabel.setWordWrap(True)
        
        # 添加到布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.contentLabel)
        
        # 自定义按钮
        self.yesButton.setText(f"请等待 ({self._remaining}s)")
        self.yesButton.setEnabled(False)
        self.cancelButton.setText("取消")
        
        # 设置对话框属性
        self.widget.setMinimumWidth(400)
        
        # 启动倒计时
        self._timer.start(1000)
    
    def _on_tick(self):
        """倒计时更新"""
        self._remaining -= 1
        
        if self._remaining <= 0:
            # 倒计时结束，启用确认按钮
            self._timer.stop()
            self.yesButton.setText("确认执行")
            self.yesButton.setEnabled(True)
        else:
            # 更新倒计时显示
            self.yesButton.setText(f"请等待 ({self._remaining}s)")


class DangerOperationDialog:
    """危险操作对话框工厂类"""
    
    @staticmethod
    def confirm_force_push(parent=None) -> bool:
        """确认强制推送"""
        dialog = DangerConfirmDialog(
            "⚠️ 危险操作：强制推送",
            "强制推送会覆盖远程分支的历史！\n\n"
            "这可能导致其他人的提交丢失。\n\n"
            "仅在以下情况使用：\n"
            "1. 修改了本地历史（amend/rebase/reset）\n"
            "2. 确认没有其他人基于这个分支开发\n\n"
            "确定要继续吗？",
            countdown=3,
            parent=parent
        )
        return dialog.exec()
    
    @staticmethod
    def confirm_reset(commit_hash: str, mode: str, count: int, parent=None) -> bool:
        """确认回滚操作"""
        mode_desc = {
            "soft": "保留所有修改在暂存区",
            "mixed": "保留工作区修改",
            "hard": "⚠️ 丢弃所有修改，不可恢复！"
        }
        
        if mode == "hard":
            countdown = 5  # hard模式倒计时更长
            warning = f"⚠️ 极度危险！\n\n"
        else:
            countdown = 3
            warning = ""
        
        content = (
            f"{warning}"
            f"将回滚到 {commit_hash[:7]}，"
            f"丢弃之后的 {count} 个提交。\n\n"
            f"模式: {mode} ({mode_desc[mode]})\n\n"
            f"如果这些提交已推送到远程，可能导致严重问题！"
        )
        
        dialog = DangerConfirmDialog(
            "⚠️ 危险操作：回滚提交",
            content,
            countdown=countdown,
            parent=parent
        )
        return dialog.exec()
    
    @staticmethod
    def confirm_delete_branch(branch: str, force: bool, parent=None) -> bool:
        """确认删除分支"""
        if force:
            content = (
                f"将强制删除分支 {branch}。\n\n"
                f"⚠️ 此分支可能包含未合并的提交！\n\n"
                f"这些提交将永久丢失。"
            )
            countdown = 3
        else:
            # 普通删除不需要倒计时
            from qfluentwidgets import MessageBox
            box = MessageBox("确认删除", f"确定要删除分支 {branch} 吗？", parent)
            return box.exec()
        
        dialog = DangerConfirmDialog(
            "⚠️ 危险操作：强制删除分支",
            content,
            countdown=countdown,
            parent=parent
        )
        return dialog.exec()
    
    @staticmethod
    def confirm_clean(file_count: int, parent=None) -> bool:
        """确认清理文件"""
        dialog = DangerConfirmDialog(
            "⚠️ 危险操作：清理文件",
            f"将删除 {file_count} 个未跟踪的文件和目录。\n\n"
            f"此操作不可恢复！\n\n"
            f"确定要继续吗？",
            countdown=3,
            parent=parent
        )
        return dialog.exec()
    
    @staticmethod
    def confirm_abort_merge(parent=None) -> bool:
        """确认中止合并"""
        dialog = DangerConfirmDialog(
            "⚠️ 确认中止合并",
            "这将放弃所有未完成的合并操作。\n\n"
            "已解决的冲突也会被撤销。\n\n"
            "确定要继续吗？",
            countdown=2,
            parent=parent
        )
        return dialog.exec()
    
    @staticmethod
    def confirm_stash_clear(count: int, parent=None) -> bool:
        """确认清空Stash"""
        dialog = DangerConfirmDialog(
            "⚠️ 危险操作：清空Stash",
            f"确定要清空所有 {count} 个Stash吗？\n\n"
            f"此操作不可恢复。",
            countdown=2,
            parent=parent
        )
        return dialog.exec()
