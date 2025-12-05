# coding:utf-8
"""
冲突解决界面 - Git merge冲突处理
显示冲突文件列表，提供解决方案选择
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QTextEdit
)
from PySide6.QtGui import QColor

from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, FluentIcon,
    InfoBar, InfoBarPosition, MessageBox, IconWidget, TitleLabel
)

from ..common.git_service import gitService, ConflictInfo
from ..common.icon import Icon


class ConflictFileCard(CardWidget):
    """冲突文件卡片"""
    resolveOurs = Signal(str)      # 使用我们的版本
    resolveTheirs = Signal(str)    # 使用他们的版本
    viewConflict = Signal(str)     # 查看冲突内容
    
    def __init__(self, conflict: ConflictInfo, parent=None):
        super().__init__(parent)
        self.conflict = conflict
        self._setup_ui()
    
    def _setup_ui(self):
        self.setFixedHeight(80)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # 左侧：冲突图标
        icon = IconWidget(Icon.GIT_CLOSE_PR, self)  # Git专用冲突图标
        icon.setFixedSize(24, 24)
        layout.addWidget(icon)
        
        # 中间：文件信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        
        # 文件路径
        path_label = StrongBodyLabel(self.conflict.path, self)
        info_layout.addWidget(path_label)
        
        # 冲突标记提示
        if self.conflict.has_conflict_markers:
            marker_label = CaptionLabel("⚠️ 包含冲突标记（<<<<<<<  >>>>>>>）", self)
            marker_label.setTextColor(QColor(220, 53, 69), QColor(220, 53, 69))
            info_layout.addWidget(marker_label)
        else:
            status_label = CaptionLabel("需要选择保留哪个版本", self)
            info_layout.addWidget(status_label)
        
        layout.addLayout(info_layout, 1)
        
        # 右侧：操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        
        # 查看冲突按钮
        if self.conflict.has_conflict_markers:
            view_btn = TransparentPushButton("查看冲突", self, FluentIcon.VIEW)
            view_btn.clicked.connect(lambda: self.viewConflict.emit(self.conflict.path))
            btn_layout.addWidget(view_btn)
        
        # 使用我们的版本
        ours_btn = PushButton("使用我们的", self, FluentIcon.ACCEPT)
        ours_btn.clicked.connect(lambda: self.resolveOurs.emit(self.conflict.path))
        btn_layout.addWidget(ours_btn)
        
        # 使用他们的版本
        theirs_btn = PushButton("使用他们的", self, FluentIcon.ACCEPT)
        theirs_btn.clicked.connect(lambda: self.resolveTheirs.emit(self.conflict.path))
        btn_layout.addWidget(theirs_btn)
        
        layout.addLayout(btn_layout)


class ConflictInterface(ScrollArea):
    """冲突解决界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("conflictInterface")
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 主容器
        container = QWidget()
        self.setWidget(container)
        
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)
        
        # 标题栏
        self._create_header(layout)
        
        # 冲突状态卡片
        self.statusCard = self._create_status_card()
        layout.addWidget(self.statusCard)
        
        # 冲突文件列表
        self.conflictListWidget = QWidget()
        self.conflictListLayout = QVBoxLayout(self.conflictListWidget)
        self.conflictListLayout.setContentsMargins(0, 0, 0, 0)
        self.conflictListLayout.setSpacing(8)
        layout.addWidget(self.conflictListWidget)
        
        layout.addStretch()
    
    def _create_header(self, parent_layout: QVBoxLayout):
        """创建顶部区域"""
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题
        title_label = TitleLabel("解决合并冲突", self)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # 刷新按钮
        refresh_btn = TransparentPushButton("刷新", self, FluentIcon.SYNC)
        refresh_btn.clicked.connect(self.refresh_conflicts)
        header_layout.addWidget(refresh_btn)
        
        # 中止合并按钮
        self.abortBtn = PushButton("中止合并", self, FluentIcon.CLOSE)
        self.abortBtn.clicked.connect(self._on_abort_merge)
        header_layout.addWidget(self.abortBtn)
        
        parent_layout.addWidget(header)
    
    def _create_status_card(self) -> CardWidget:
        """创建状态卡片"""
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        
        # 状态图标和文本
        status_layout = QHBoxLayout()
        self.statusIcon = IconWidget(FluentIcon.INFO, self)
        self.statusIcon.setFixedSize(32, 32)
        status_layout.addWidget(self.statusIcon)
        
        info_layout = QVBoxLayout()
        self.statusTitle = StrongBodyLabel("正在检测冲突...", self)
        info_layout.addWidget(self.statusTitle)
        
        self.statusDesc = CaptionLabel("", self)
        info_layout.addWidget(self.statusDesc)
        
        status_layout.addLayout(info_layout, 1)
        layout.addLayout(status_layout)
        
        return card
    
    def _connect_signals(self):
        """连接信号"""
        gitService.statusChanged.connect(self.refresh_conflicts)
    
    def refresh_conflicts(self):
        """刷新冲突列表（异步）"""
        from app.common.async_helper import SimpleAsyncTask
        
        def fetch_data():
            """在子线程获取数据"""
            is_merging = gitService.is_merging()
            conflicts = gitService.get_conflicts() if is_merging else []
            return is_merging, conflicts
        
        def update_ui(result):
            """在主线程更新UI"""
            is_merging, conflicts = result
            
            if not is_merging:
                self.statusIcon.setIcon(FluentIcon.ACCEPT)
                self.statusTitle.setText("当前没有合并冲突")
                self.statusDesc.setText("所有文件已解决或没有进行中的合并操作")
                self.abortBtn.setEnabled(False)
                self._clear_conflict_list()
                return
            
            if not conflicts:
                self.statusIcon.setIcon(FluentIcon.ACCEPT)
                self.statusTitle.setText("所有冲突已解决")
                self.statusDesc.setText("可以继续提交完成合并")
                self.abortBtn.setEnabled(True)
            else:
                self.statusIcon.setIcon(FluentIcon.CANCEL)
                self.statusTitle.setText(f"发现 {len(conflicts)} 个冲突文件")
                self.statusDesc.setText("请选择保留哪个版本，或手动编辑解决冲突")
                self.abortBtn.setEnabled(True)
            
            self._update_conflict_list(conflicts)
        
        SimpleAsyncTask.run(fetch_data, update_ui)
    
    def _clear_conflict_list(self):
        """清空冲突列表"""
        while self.conflictListLayout.count():
            item = self.conflictListLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _update_conflict_list(self, conflicts: list[ConflictInfo]):
        """更新冲突文件列表"""
        # 清空现有列表
        self._clear_conflict_list()
        
        # 添加冲突文件卡片
        for conflict in conflicts:
            card = ConflictFileCard(conflict, self)
            card.resolveOurs.connect(self._on_resolve_ours)
            card.resolveTheirs.connect(self._on_resolve_theirs)
            card.viewConflict.connect(self._on_view_conflict)
            self.conflictListLayout.addWidget(card)
    
    def _on_resolve_ours(self, file_path: str):
        """使用我们的版本解决冲突（异步）"""
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(
                    title="成功",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
                self.refresh_conflicts()
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000
                )
        
        AsyncTask.run(
            func=lambda: gitService.resolve_conflict_with_ours(file_path),
            on_success=on_success,
            progress_title='请稍候',
            progress_content=f'正在解决冲突: {file_path}',
            parent=self.window()
        )
    
    def _on_resolve_theirs(self, file_path: str):
        """使用他们的版本解决冲突（异步）"""
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(
                    title="成功",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
                self.refresh_conflicts()
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000
                )
        
        AsyncTask.run(
            func=lambda: gitService.resolve_conflict_with_theirs(file_path),
            on_success=on_success,
            progress_title='请稍候',
            progress_content=f'正在解决冲突: {file_path}',
            parent=self.window()
        )
    
    def _on_view_conflict(self, file_path: str):
        """查看冲突内容（异步）"""
        from app.common.async_helper import SimpleAsyncTask
        import os
        
        def read_conflict_file():
            full_path = os.path.join(gitService.repo_path, file_path)
            real_path = os.path.realpath(full_path)
            repo_real_path = os.path.realpath(gitService.repo_path)
            
            if not real_path.startswith(repo_real_path + os.sep):
                raise ValueError("路径不在仓库内")
            
            with open(real_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        
        def on_success(content):
            from .conflict_viewer_dialog import ConflictViewerDialog
            dialog = ConflictViewerDialog(file_path, content, self.window())
            dialog.exec()
        
        def on_error(error_msg):
            InfoBar.error(
                title="读取失败",
                content=f"无法读取文件: {error_msg}",
                parent=self.window(),
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=3000
            )
        
        # 使用封装的异步工具
        SimpleAsyncTask.run(read_conflict_file, on_success)
    
    def _on_abort_merge(self):
        """中止合并操作"""
        from app.common.danger_dialog import DangerOperationDialog
        
        if DangerOperationDialog.confirm_abort_merge(self.window()):
            from app.common.async_helper import AsyncTask
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success(
                        title="成功",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM_RIGHT,
                        duration=2000
                    )
                    self.refresh_conflicts()
                else:
                    InfoBar.error(
                        title="失败",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM_RIGHT,
                        duration=3000
                    )
            
            AsyncTask.run(
                func=gitService.abort_merge,
                on_success=on_success,
                progress_title='请稍候',
                progress_content='正在中止合并...',
                parent=self.window()
            )
    
    def showEvent(self, event):
        """显示时自动刷新"""
        super().showEvent(event)
        self.refresh_conflicts()
