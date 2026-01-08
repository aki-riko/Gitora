# coding:utf-8
"""
Tag标签管理界面
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame

from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PushButton, TransparentPushButton, FluentIcon, InfoBar, InfoBarPosition,
    LineEdit, MessageBoxBase, MessageBox, IconWidget, SubtitleLabel, TextEdit,
    ToolTipFilter, ToolTipPosition
)

from ..common.git_service import gitService
from ..common.icon import Icon
from ..common.logger import get_logger

logger = get_logger("TagInterface")


class CreateTagDialog(MessageBoxBase):
    """创建Tag对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_content()
    
    def _setup_content(self):
        # 标题
        self.titleLabel = SubtitleLabel(self.tr("创建Tag"), self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # 描述
        self.descLabel = BodyLabel(self.tr("输入Tag信息"), self)
        self.viewLayout.addWidget(self.descLabel)
        
        # Tag名称
        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText(self.tr("Tag名称，如: v1.0.0"))
        self.nameEdit.setClearButtonEnabled(True)
        self.viewLayout.addWidget(self.nameEdit)
        
        # Tag消息（可选）
        self.messageEdit = TextEdit(self)
        self.messageEdit.setPlaceholderText(self.tr("Tag消息（可选）\n如果填写，将创建附注Tag"))
        self.messageEdit.setFixedHeight(80)
        self.viewLayout.addWidget(self.messageEdit)
        
        # 设置最小宽度
        self.widget.setMinimumWidth(350)
    
    def get_tag_info(self) -> tuple[str, str]:
        """获取Tag信息 (name, message)"""
        return self.nameEdit.text().strip(), self.messageEdit.toPlainText().strip()


class TagCard(CardWidget):
    """Tag卡片"""
    checkoutClicked = Signal(str)
    deleteClicked = Signal(str)
    pushClicked = Signal(str)
    
    def __init__(self, tag_name: str, commit_hash: str, message: str, parent=None):
        super().__init__(parent)
        self.tag_name = tag_name
        self.commit_hash = commit_hash
        self.message = message
        self._setup_ui()
    
    def _setup_ui(self):
        self.setFixedHeight(64)  # 统一卡片高度
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 图标
        icon = IconWidget(FluentIcon.TAG, self)
        icon.setFixedSize(24, 24)
        layout.addWidget(icon)
        
        # Tag信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        # Tag名称
        name_label = StrongBodyLabel(self.tag_name, self)
        info_layout.addWidget(name_label)
        
        # 提交hash和消息
        detail_text = f"{self.commit_hash}"
        if self.message:
            detail_text += f" - {self.message}"
        detail_label = CaptionLabel(detail_text, self)
        info_layout.addWidget(detail_label)
        
        layout.addLayout(info_layout, 1)
        
        # 操作按钮
        checkout_btn = TransparentPushButton(self.tr("切换"), self, Icon.GIT_COMMIT)
        checkout_btn.clicked.connect(lambda: self.checkoutClicked.emit(self.tag_name))
        layout.addWidget(checkout_btn)
        
        push_btn = TransparentPushButton(self.tr("推送"), self, FluentIcon.SEND)
        push_btn.clicked.connect(lambda: self.pushClicked.emit(self.tag_name))
        layout.addWidget(push_btn)
        
        delete_btn = TransparentPushButton(self.tr("删除"), self, FluentIcon.DELETE)
        delete_btn.clicked.connect(lambda: self.deleteClicked.emit(self.tag_name))
        layout.addWidget(delete_btn)


class TagInterface(ScrollArea):
    """Tag管理界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tagInterface")
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        self.setWidgetResizable(True)
        
        container = QWidget()
        self.setWidget(container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)
        
        # 顶部
        self._create_header(layout)
        
        # Tag列表
        self.tagListWidget = QWidget()
        self.tagListLayout = QVBoxLayout(self.tagListWidget)
        self.tagListLayout.setContentsMargins(0, 0, 0, 0)
        self.tagListLayout.setSpacing(8)
        layout.addWidget(self.tagListWidget)
        
        layout.addStretch()
    
    def _create_header(self, parent_layout: QVBoxLayout):
        """创建顶部区域"""
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_label = SubtitleLabel(self.tr("标签管理 (Tag)"), self)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 刷新按钮
        refresh_btn = TransparentPushButton(self.tr("刷新"), self, FluentIcon.SYNC)
        refresh_btn.setToolTip(self.tr("重新加载标签列表"))
        refresh_btn.installEventFilter(ToolTipFilter(refresh_btn, 500, ToolTipPosition.BOTTOM))
        refresh_btn.clicked.connect(self.refresh_tags)
        header_layout.addWidget(refresh_btn)
        
        # 推送所有Tag
        push_all_btn = PushButton(self.tr("推送所有"), self, FluentIcon.SEND)
        push_all_btn.setToolTip(self.tr("将所有本地标签推送到远程仓库"))
        push_all_btn.installEventFilter(ToolTipFilter(push_all_btn, 500, ToolTipPosition.BOTTOM))
        push_all_btn.clicked.connect(self._on_push_all_tags)
        header_layout.addWidget(push_all_btn)
        
        # 创建Tag按钮
        create_btn = PushButton(self.tr("创建标签 (Tag)"), self, FluentIcon.ADD)
        create_btn.setToolTip(self.tr("在当前提交上创建新的标签\n标签可用于标记版本号或重要节点"))
        create_btn.installEventFilter(ToolTipFilter(create_btn, 500, ToolTipPosition.BOTTOM))
        create_btn.clicked.connect(self._on_create_tag)
        header_layout.addWidget(create_btn)
        
        parent_layout.addWidget(header)
    
    def _connect_signals(self):
        """连接信号"""
        gitService.statusChanged.connect(self.refresh_tags)
    
    def refresh_tags(self):
        """刷新Tag列表（异步）"""
        if not gitService.repo_path:
            return
        
        from app.common.async_helper import SimpleAsyncTask
        
        def fetch_tags():
            return gitService.get_tags()
        
        def update_ui(tags):
            """在主线程更新UI"""
            # 清空列表
            while self.tagListLayout.count():
                item = self.tagListLayout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            if not tags:
                # 空状态
                empty_label = BodyLabel(self.tr("暂无Tag"), self)
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tagListLayout.addWidget(empty_label)
                return
            
            # 添加Tag卡片
            for tag_name, commit_hash, message in tags:
                card = TagCard(tag_name, commit_hash, message, self)
                card.checkoutClicked.connect(self._on_checkout_tag)
                card.deleteClicked.connect(self._on_delete_tag)
                card.pushClicked.connect(self._on_push_tag)
                self.tagListLayout.addWidget(card)
        
        SimpleAsyncTask.run(fetch_tags, update_ui)
    
    def _on_create_tag(self):
        """创建Tag"""
        dialog = CreateTagDialog(self.window())
        if dialog.exec():
            name, message = dialog.get_tag_info()
            if not name:
                InfoBar.warning(self.tr("提示"), self.tr("请输入Tag名称"), parent=self.window(), position=InfoBarPosition.BOTTOM)
                return
            
            from app.common.async_helper import AsyncTask
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success(self.tr("成功"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
                    self.refresh_tags()
                else:
                    InfoBar.error(self.tr("失败"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
            
            AsyncTask.run(
                func=lambda: gitService.create_tag(name, message),
                on_success=on_success,
                progress_title=self.tr('请稍候'),
                progress_content=self.tr('正在创建Tag: %s') % name,
                parent=self.window()
            )
    
    def _on_delete_tag(self, tag_name: str):
        """删除Tag"""
        box = MessageBox(self.tr("确认删除"), self.tr("确定要删除Tag '%s' 吗？") % tag_name, self.window())
        if box.exec():
            from app.common.async_helper import SimpleAsyncTask
            
            def on_finished(result):
                success, msg = result
                if success:
                    InfoBar.success(self.tr("成功"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
                    self.refresh_tags()
                else:
                    InfoBar.error(self.tr("失败"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
            
            SimpleAsyncTask.run(lambda: gitService.delete_tag(tag_name), on_finished)
    
    def _on_push_tag(self, tag_name: str):
        """推送Tag（异步）"""
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(self.tr("成功"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
            else:
                InfoBar.error(self.tr("失败"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
        
        AsyncTask.run(
            func=lambda: gitService.push_tag(tag_name),
            on_success=on_success,
            progress_title=self.tr('请稍候'),
            progress_content=self.tr('正在推送Tag: %s') % tag_name,
            parent=self.window()
        )
    
    def _on_push_all_tags(self):
        """推送所有Tag（异步）"""
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(self.tr("成功"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
            else:
                InfoBar.error(self.tr("失败"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
        
        AsyncTask.run(
            func=gitService.push_all_tags,
            on_success=on_success,
            progress_title=self.tr('请稍候'),
            progress_content=self.tr('正在推送所有Tag...'),
            parent=self.window()
        )
    
    def _on_checkout_tag(self, tag_name: str):
        """切换到Tag"""
        box = MessageBox(
            self.tr("确认切换"),
            self.tr("切换到Tag '%s' 将进入分离头指针状态。\n确定继续吗？") % tag_name,
            self.window()
        )
        if box.exec():
            from app.common.async_helper import AsyncTask
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success(self.tr("成功"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
                else:
                    InfoBar.error(self.tr("失败"), msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
            
            AsyncTask.run(
                func=lambda: gitService.checkout_tag(tag_name),
                on_success=on_success,
                progress_title=self.tr('请稍候'),
                progress_content=self.tr('正在切换到Tag: %s') % tag_name,
                parent=self.window()
            )
    
    def showEvent(self, event):
        """显示时自动刷新"""
        super().showEvent(event)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self.refresh_tags)
