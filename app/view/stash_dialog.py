# coding:utf-8
"""
Stash管理对话框
显示stash列表，提供保存、恢复、删除操作
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget

from qfluentwidgets import (
    Dialog, PushButton, TransparentPushButton, FluentIcon,
    InfoBar, InfoBarPosition, MessageBox, LineEdit,
    BodyLabel, CaptionLabel, StrongBodyLabel, CardWidget,
    ScrollArea, ToolTipFilter, ToolTipPosition
)

from ..common.git_service import gitService
from ..common.logger import get_logger

logger = get_logger("StashDialog")


class StashItemCard(CardWidget):
    """Stash条目卡片"""
    
    def __init__(self, stash_id: str, message: str, parent=None):
        super().__init__(parent)
        self.stash_id = stash_id
        self.message = message
        self._setup_ui()
    
    def _setup_ui(self):
        self.setFixedHeight(80)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 左侧：Stash信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        # Stash ID
        id_label = StrongBodyLabel(self.stash_id, self)
        info_layout.addWidget(id_label)
        
        # Stash消息
        msg_label = CaptionLabel(self.message, self)
        info_layout.addWidget(msg_label)
        
        layout.addLayout(info_layout, 1)
        
        # 右侧：操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # 应用按钮（恢复但不删除）
        apply_btn = TransparentPushButton("应用", self, FluentIcon.COPY)
        apply_btn.setToolTip("恢复此保存的内容，但保留记录（可多次使用）")
        apply_btn.installEventFilter(ToolTipFilter(apply_btn, 500, ToolTipPosition.TOP))
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)
        
        # 恢复按钮（恢复并删除）
        pop_btn = PushButton("恢复", self, FluentIcon.DOWNLOAD)
        pop_btn.setToolTip("恢复此保存的内容，并删除记录（一次性）")
        pop_btn.installEventFilter(ToolTipFilter(pop_btn, 500, ToolTipPosition.TOP))
        pop_btn.clicked.connect(self._on_pop)
        btn_layout.addWidget(pop_btn)
        
        # Delete按钮
        delete_btn = TransparentPushButton("删除", self, FluentIcon.DELETE)
        delete_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(delete_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_apply(self):
        """应用stash（异步）"""
        from app.common.async_helper import AsyncTask
        
        stash_id = self.stash_id
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(
                    title="成功",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=2000
                )
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=3000
                )
        
        AsyncTask.run(
            func=lambda: gitService.stash_apply(stash_id),
            on_success=on_success,
            progress_title='请稍候',
            progress_content=f'正在应用stash: {stash_id}',
            parent=self.window()
        )
    
    def _on_pop(self):
        """恢复stash（异步）"""
        from app.common.async_helper import AsyncTask
        
        stash_id = self.stash_id
        parent_dialog = self.parent().parent()
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(
                    title="成功",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=2000
                )
                # 刷新列表
                if hasattr(parent_dialog, 'refresh_stash_list'):
                    parent_dialog.refresh_stash_list()
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=3000
                )
        
        AsyncTask.run(
            func=lambda: gitService.stash_pop(stash_id),
            on_success=on_success,
            progress_title='请稍候',
            progress_content=f'正在恢复stash: {stash_id}',
            parent=self.window()
        )
    
    def _on_delete(self):
        """删除stash"""
        box = MessageBox(
            "确认删除",
            f"确定要删除 {self.stash_id} 吗？\n\n此操作不可恢复。",
            self.window()
        )
        box.yesButton.setText("确认删除")
        box.cancelButton.setText("取消")
        
        if box.exec():
            from app.common.async_helper import AsyncTask
            
            stash_id = self.stash_id
            parent_dialog = self.parent().parent()
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success(
                        title="成功",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=2000
                    )
                    # 刷新列表
                    if hasattr(parent_dialog, 'refresh_stash_list'):
                        parent_dialog.refresh_stash_list()
                else:
                    InfoBar.error(
                        title="失败",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=3000
                    )
            
            AsyncTask.run(
                func=lambda: gitService.stash_drop(stash_id),
                on_success=on_success,
                progress_title='请稍候',
                progress_content=f'正在删除stash: {stash_id}',
                parent=self.window()
            )


class StashDialog(Dialog):
    """Stash管理对话框"""
    
    def __init__(self, parent=None):
        super().__init__("临时保存 (Stash)", "保存当前修改，稍后恢复（类似草稿箱）", parent)
        self._setup_ui()
        self.refresh_stash_list()
    
    def _setup_ui(self):
        # 设置对话框大小
        self.setFixedSize(700, 500)
        
        # 顶部操作栏
        top_layout = QHBoxLayout()
        
        # 创建临时保存
        self.messageEdit = LineEdit(self)
        self.messageEdit.setPlaceholderText("备注信息（可选）")
        self.messageEdit.setFixedWidth(300)
        top_layout.addWidget(self.messageEdit)
        
        save_btn = PushButton("保存当前修改", self, FluentIcon.SAVE)
        save_btn.setToolTip("将当前工作区的所有修改保存到储藏区\n工作区会恢复到干净状态")
        save_btn.installEventFilter(ToolTipFilter(save_btn, 500, ToolTipPosition.BOTTOM))
        save_btn.clicked.connect(self._on_save_stash)
        top_layout.addWidget(save_btn)
        
        top_layout.addStretch()
        
        # 刷新按钮
        refresh_btn = TransparentPushButton("刷新", self, FluentIcon.SYNC)
        refresh_btn.setToolTip("重新加载储藏列表")
        refresh_btn.installEventFilter(ToolTipFilter(refresh_btn, 500, ToolTipPosition.BOTTOM))
        refresh_btn.clicked.connect(self.refresh_stash_list)
        top_layout.addWidget(refresh_btn)
        
        # 清空所有按钮
        clear_btn = TransparentPushButton("清空所有", self, FluentIcon.DELETE)
        clear_btn.setToolTip("删除所有储藏记录\n此操作不可恢复")
        clear_btn.installEventFilter(ToolTipFilter(clear_btn, 500, ToolTipPosition.BOTTOM))
        clear_btn.clicked.connect(self._on_clear_all)
        top_layout.addWidget(clear_btn)
        
        self.textLayout.addLayout(top_layout)
        
        # 保存列表容器
        list_label = BodyLabel("保存列表:", self)
        self.textLayout.addWidget(list_label)
        
        # 滚动区域
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(300)
        
        self.stashListWidget = QWidget()
        self.stashListLayout = QVBoxLayout(self.stashListWidget)
        self.stashListLayout.setContentsMargins(0, 0, 0, 0)
        self.stashListLayout.setSpacing(8)
        self.stashListLayout.addStretch()
        
        scroll.setWidget(self.stashListWidget)
        self.textLayout.addWidget(scroll)
        
        # 修改按钮文本
        self.yesButton.setText("关闭")
        self.cancelButton.hide()
    
    def refresh_stash_list(self):
        """刷新Stash列表"""
        # 清空现有列表
        while self.stashListLayout.count() > 1:  # 保留最后的stretch
            item = self.stashListLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 获取Stash列表
        stashes = gitService.stash_list()
        
        if not stashes:
            # 显示空状态
            empty_label = BodyLabel("暂无保存记录", self)
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.stashListLayout.insertWidget(0, empty_label)
        else:
            # 添加Stash卡片
            for stash_id, message in stashes:
                card = StashItemCard(stash_id, message, self.stashListWidget)
                self.stashListLayout.insertWidget(
                    self.stashListLayout.count() - 1,  # 插入到stretch之前
                    card
                )
    
    def _on_save_stash(self):
        """保存到Stash"""
        message = self.messageEdit.text().strip()
        
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(
                    title="成功",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=2000
                )
                self.messageEdit.clear()
                self.refresh_stash_list()
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=3000
                )
        
        AsyncTask.run(
            func=lambda: gitService.stash_save(message),
            on_success=on_success,
            progress_title='请稍候',
            progress_content='正在保存到stash...',
            parent=self.window()
        )
    
    def _on_clear_all(self):
        """清空所有Stash"""
        stashes = gitService.stash_list()
        if not stashes:
            InfoBar.warning(
                title="提示",
                content="没有可清空的Stash",
                parent=self.window(),
                position=InfoBarPosition.BOTTOM,
                duration=2000
            )
            return
        
        from app.common.danger_dialog import DangerOperationDialog
        
        if DangerOperationDialog.confirm_stash_clear(len(stashes), self.window()):
            from app.common.async_helper import AsyncTask
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success(
                        title="成功",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=2000
                    )
                    self.refresh_stash_list()
                else:
                    InfoBar.error(
                        title="失败",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=3000
                    )
            
            AsyncTask.run(
                func=gitService.stash_clear,
                on_success=on_success,
                progress_title='请稍候',
                progress_content='正在清空所有stash...',
                parent=self.window()
            )
