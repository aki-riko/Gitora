# coding:utf-8
"""
历史界面 - 提交历史时间线展示
使用TimeLineWidget展示Git提交记录
支持虚拟滚动和右侧面板固定
"""
from functools import lru_cache
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSplitter, QScrollArea
)
from PySide6.QtGui import QColor, QFont

from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PushButton, TransparentPushButton, FluentIcon, InfoBar, InfoBarPosition,
    setFont, IconWidget, TitleLabel, SubtitleLabel, PrimaryPushButton,
    SearchLineEdit, ToolTipFilter, ToolTipPosition, MessageBox, ComboBox,
    InfoBarIcon, SmoothScrollArea
)
from qfluentwidgetspro import TimeLineWidget, TimeLineCard, Splitter

from app.common.git_service import gitService, CommitInfo
from app.common.logger import get_logger

logger = get_logger("HistoryInterface")


class CountdownButton(QWidget):
    """倒计时按钮 - 用于危险操作的确认
    
    点击后开始倒计时，倒计时结束前再次点击才会执行操作。
    这样可以防止误操作。
    """
    confirmed = Signal()  # 确认执行信号
    
    def __init__(self, text: str, countdown: int = 3, parent=None, icon=None):
        super().__init__(parent)
        self._original_text = text
        self._countdown = countdown
        self._remaining = 0
        self._is_counting = False
        
        # 创建内部按钮
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._button = PushButton(text, self, icon)
        layout.addWidget(self._button)
        
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        
        self._button.clicked.connect(self._on_click)
    
    def _on_click(self):
        """点击事件"""
        if self._is_counting:
            # 正在倒计时中再次点击 = 确认执行
            self._timer.stop()
            self._is_counting = False
            self._button.setText(self._original_text)
            self.confirmed.emit()
        else:
            # 首次点击，开始倒计时
            self._is_counting = True
            self._remaining = self._countdown
            self._update_text()
            self._timer.start(1000)
    
    def _on_tick(self):
        """每秒更新"""
        self._remaining -= 1
        if self._remaining <= 0:
            # 倒计时结束，重置状态
            self._timer.stop()
            self._is_counting = False
            self._button.setText(self._original_text)
        else:
            self._update_text()
    
    def _update_text(self):
        """更新按钮文本"""
        self._button.setText(f"再次点击确认 ({self._remaining}s)")
    
    def reset(self):
        """重置按钮状态"""
        self._timer.stop()
        self._is_counting = False
        self._remaining = 0
        self._button.setText(self._original_text)
    
    def setEnabled(self, enabled: bool):
        """设置启用状态"""
        self._button.setEnabled(enabled)


from app.common.style_sheet import StyleSheet


class CommitCard(CardWidget):
    """提交信息卡片"""
    clicked = Signal(CommitInfo)
    cherryPickClicked = Signal(str)  # commit_hash
    viewDetailClicked = Signal(str)  # commit_hash

    def __init__(self, commit: CommitInfo, parent=None):
        super().__init__(parent)
        self.commit = commit
        self._setup_ui()
        
        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # 第一行：提交信息
        self.messageLabel = StrongBodyLabel(self.commit.message, self)
        self.messageLabel.setWordWrap(True)
        layout.addWidget(self.messageLabel)

        # 第二行：作者和时间
        info_layout = QHBoxLayout()
        info_layout.setSpacing(16)

        # 作者
        author_layout = QHBoxLayout()
        author_layout.setSpacing(4)
        author_icon = IconWidget(FluentIcon.PEOPLE, self)
        author_icon.setFixedSize(14, 14)
        author_layout.addWidget(author_icon)
        author_label = CaptionLabel(self.commit.author, self)
        author_layout.addWidget(author_label)
        info_layout.addLayout(author_layout)

        # 时间
        time_layout = QHBoxLayout()
        time_layout.setSpacing(4)
        time_icon = IconWidget(FluentIcon.CALENDAR, self)
        time_icon.setFixedSize(14, 14)
        time_layout.addWidget(time_icon)
        time_label = CaptionLabel(self.commit.date, self)
        time_layout.addWidget(time_label)
        info_layout.addLayout(time_layout)

        # Hash
        hash_layout = QHBoxLayout()
        hash_layout.setSpacing(4)
        hash_icon = IconWidget(FluentIcon.TAG, self)
        hash_icon.setFixedSize(14, 14)
        hash_layout.addWidget(hash_icon)
        hash_label = CaptionLabel(self.commit.short_hash, self)
        hash_label.setTextColor(QColor(100, 100, 100), QColor(180, 180, 180))
        hash_layout.addWidget(hash_label)
        info_layout.addLayout(hash_layout)

        info_layout.addStretch()
        layout.addLayout(info_layout)

        # 点击事件
        super().clicked.connect(lambda: self.clicked.emit(self.commit))
    
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        from qfluentwidgets import RoundMenu, Action
        menu = RoundMenu(parent=self)
        
        # 查看详情
        detail_action = Action(FluentIcon.INFO, "查看详情")
        detail_action.triggered.connect(lambda: self.viewDetailClicked.emit(self.commit.hash))
        menu.addAction(detail_action)
        
        menu.addSeparator()
        
        # Cherry-pick
        cherry_pick_action = Action(FluentIcon.COPY, "Cherry-pick此提交")
        cherry_pick_action.triggered.connect(lambda: self.cherryPickClicked.emit(self.commit.hash))
        menu.addAction(cherry_pick_action)
        
        menu.exec(self.mapToGlobal(pos))


class CommitDetailPanel(QFrame):
    """提交详情面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("commitDetailPanel")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        self.titleLabel = TitleLabel("提交详情", self)
        layout.addWidget(self.titleLabel)

        # 提交信息
        self.messageLabel = StrongBodyLabel("", self)
        self.messageLabel.setWordWrap(True)
        layout.addWidget(self.messageLabel)

        # 详情信息卡片
        detail_card = CardWidget(self)
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(16, 16, 16, 16)
        detail_layout.setSpacing(12)

        # Hash
        hash_row = QHBoxLayout()
        hash_row.addWidget(CaptionLabel("Hash:", self))
        self.hashLabel = BodyLabel("", self)
        self.hashLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        hash_row.addWidget(self.hashLabel, 1)
        detail_layout.addLayout(hash_row)

        # 作者
        author_row = QHBoxLayout()
        author_row.addWidget(CaptionLabel("作者:", self))
        self.authorLabel = BodyLabel("", self)
        author_row.addWidget(self.authorLabel, 1)
        detail_layout.addLayout(author_row)

        # 邮箱
        email_row = QHBoxLayout()
        email_row.addWidget(CaptionLabel("邮箱:", self))
        self.emailLabel = BodyLabel("", self)
        email_row.addWidget(self.emailLabel, 1)
        detail_layout.addLayout(email_row)

        # 时间
        date_row = QHBoxLayout()
        date_row.addWidget(CaptionLabel("时间:", self))
        self.dateLabel = BodyLabel("", self)
        date_row.addWidget(self.dateLabel, 1)
        detail_layout.addLayout(date_row)

        # 分支
        branch_row = QHBoxLayout()
        branch_row.addWidget(CaptionLabel("分支:", self))
        self.branchLabel = BodyLabel("", self)
        branch_row.addWidget(self.branchLabel, 1)
        detail_layout.addLayout(branch_row)

        layout.addWidget(detail_card)

        # 操作按钮 - 第一行（安全操作）
        btn_layout = QHBoxLayout()
        self.copyHashBtn = PushButton("复制Hash", self, FluentIcon.COPY)
        self.copyHashBtn.clicked.connect(self._copy_hash)
        btn_layout.addWidget(self.copyHashBtn)

        self.checkoutBtn = PushButton("检出此提交", self, FluentIcon.SYNC)
        self.checkoutBtn.clicked.connect(self._checkout_commit)
        btn_layout.addWidget(self.checkoutBtn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 操作按钮 - 第二行（撤销操作，安全）
        revert_layout = QHBoxLayout()
        self.revertBtn = PushButton("撤销此提交", self, FluentIcon.CANCEL)
        self.revertBtn.setToolTip("创建一个新提交来撤销此提交的更改（安全，不修改历史）")
        self.revertBtn.installEventFilter(ToolTipFilter(self.revertBtn, 500, ToolTipPosition.TOP))
        self.revertBtn.clicked.connect(self._revert_commit)
        revert_layout.addWidget(self.revertBtn)
        revert_layout.addStretch()
        layout.addLayout(revert_layout)

        # 危险操作区域
        danger_card = CardWidget(self)
        danger_card.setObjectName("dangerCard")
        danger_layout = QVBoxLayout(danger_card)
        danger_layout.setContentsMargins(12, 12, 12, 12)
        danger_layout.setSpacing(8)

        # 警告标题
        warning_layout = QHBoxLayout()
        warning_icon = IconWidget(FluentIcon.CANCEL, self)
        warning_icon.setFixedSize(16, 16)
        warning_layout.addWidget(warning_icon)
        warning_label = CaptionLabel("危险操作", self)
        warning_label.setTextColor(QColor(220, 53, 69), QColor(220, 53, 69))
        warning_layout.addWidget(warning_label)
        warning_layout.addStretch()
        danger_layout.addLayout(warning_layout)

        # 回滚说明
        self.resetInfoLabel = CaptionLabel("回滚将丢弃此提交之后的所有提交", self)
        danger_layout.addWidget(self.resetInfoLabel)

        # 回滚模式选择
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(CaptionLabel("模式:", self))
        self.resetModeCombo = ComboBox(self)
        self.resetModeCombo.addItems([
            "🟢 混合 (Mixed) - 保留文件修改，清空暂存",
            "🟡 软 (Soft) - 保留所有修改，可重新提交",
            "🔴 硬 (Hard) - 完全丢弃，不可恢复！"
        ])
        self.resetModeCombo.setCurrentIndex(0)
        self.resetModeCombo.setToolTip(
            "🟢 混合模式 (Mixed):\n"
            "  · 保留工作区的文件修改\n"
            "  · 清空暂存区\n"
            "  · 适合：重新整理提交\n\n"
            "🟡 软模式 (Soft):\n"
            "  · 保留工作区和暂存区\n"
            "  · 可直接重新提交\n"
            "  · 适合：修改提交信息\n\n"
            "🔴 硬模式 (Hard):\n"
            "  · 完全丢弃所有修改\n"
            "  · 文件恢复到指定提交状态\n"
            "  · ⚠️ 不可恢复，极度危险！"
        )
        self.resetModeCombo.installEventFilter(ToolTipFilter(self.resetModeCombo, 500, ToolTipPosition.TOP))
        mode_layout.addWidget(self.resetModeCombo, 1)
        danger_layout.addLayout(mode_layout)

        # 回滚按钮（带倒计时）
        self.resetBtn = CountdownButton("回滚到此提交", countdown=3, parent=self, icon=FluentIcon.DELETE)
        self.resetBtn.confirmed.connect(self._reset_to_commit)
        danger_layout.addWidget(self.resetBtn)

        layout.addWidget(danger_card)

        layout.addStretch()

        # 初始隐藏详情
        self._current_commit = None
        self.set_commit(None)

    def set_commit(self, commit: CommitInfo):
        """设置当前提交"""
        self._current_commit = commit
        
        # 重置倒计时按钮状态
        self.resetBtn.reset()

        if commit:
            self.messageLabel.setText(commit.message)
            self.hashLabel.setText(commit.hash)
            self.authorLabel.setText(commit.author)
            self.emailLabel.setText(commit.email)
            self.dateLabel.setText(commit.date)
            self.branchLabel.setText(commit.branch)
            self.copyHashBtn.setEnabled(True)
            self.checkoutBtn.setEnabled(True)
            self.revertBtn.setEnabled(True)
            self.resetBtn.setEnabled(True)
            
            # 更新回滚信息
            count = gitService.get_commit_count_after(commit.hash)
            if count > 0:
                self.resetInfoLabel.setText(f"回滚将丢弃此提交之后的 {count} 个提交")
            elif count == 0:
                self.resetInfoLabel.setText("这是最新提交，无需回滚")
                self.resetBtn.setEnabled(False)
            else:
                self.resetInfoLabel.setText("回滚将丢弃此提交之后的所有提交")
        else:
            self.messageLabel.setText("选择一个提交查看详情")
            self.hashLabel.setText("-")
            self.authorLabel.setText("-")
            self.emailLabel.setText("-")
            self.dateLabel.setText("-")
            self.branchLabel.setText("-")
            self.copyHashBtn.setEnabled(False)
            self.checkoutBtn.setEnabled(False)
            self.revertBtn.setEnabled(False)
            self.resetBtn.setEnabled(False)
            self.resetInfoLabel.setText("回滚将丢弃此提交之后的所有提交")

    def _copy_hash(self):
        """复制Hash到剪贴板"""
        if self._current_commit:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._current_commit.hash)
            InfoBar.success(
                title="成功",
                content="已复制Hash到剪贴板",
                parent=self.window(),
                position=InfoBarPosition.BOTTOM,
                duration=2000
            )

    def _checkout_commit(self):
        """检出此提交（异步）"""
        if not self._current_commit:
            return
        
        from app.common.async_helper import AsyncTask
        
        commit_hash = self._current_commit.short_hash
        
        def on_success(result):
            success, msg = result
            if success:
                InfoBar.success(
                    title="成功",
                    content=f"已检出到 {commit_hash}",
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
            func=lambda: gitService.checkout_branch(commit_hash),
            on_success=on_success,
            progress_title='请稍候',
            progress_content=f'正在检出到 {commit_hash}...',
            parent=self.window()
        )

    def _revert_commit(self):
        """撤销此提交（创建新的撤销提交，安全操作）"""
        if not self._current_commit:
            return
        
        # 确认对话框
        box = MessageBox(
            "撤销提交",
            f"将创建一个新提交来撤销 {self._current_commit.short_hash} 的更改。\n\n"
            "这是安全操作，不会修改Git历史。",
            self.window()
        )
        box.yesButton.setText("确认撤销")
        box.cancelButton.setText("取消")
        
        if box.exec():
            from app.common.async_helper import AsyncTask
            
            commit_hash = self._current_commit.hash
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success(
                        title="成功",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=3000
                    )
                else:
                    InfoBar.error(
                        title="撤销失败",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=4000
                    )
            
            AsyncTask.run(
                func=lambda: gitService.revert_commit(commit_hash),
                on_success=on_success,
                progress_title='请稍候',
                progress_content='正在撤销提交...',
                parent=self.window()
            )

    def _reset_to_commit(self):
        """回滚到此提交（危险操作，会修改历史）"""
        if not self._current_commit:
            return
        
        from app.common.danger_dialog import DangerOperationDialog
        
        # 获取回滚模式
        mode_text = self.resetModeCombo.currentText()
        if "混合" in mode_text:
            mode = "mixed"
        elif "软" in mode_text:
            mode = "soft"
        else:
            mode = "hard"
        
        # 获取将要丢弃的提交数量
        count = gitService.get_commit_count_after(self._current_commit.hash)
        
        # 使用统一的危险操作对话框
        if DangerOperationDialog.confirm_reset(
            self._current_commit.hash, mode, count, self.window()
        ):
            from app.common.async_helper import AsyncTask
            
            commit_hash = self._current_commit.hash
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success(
                        title="回滚成功",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=3000
                    )
                else:
                    InfoBar.error(
                        title="回滚失败",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=4000
                    )
            
            AsyncTask.run(
                func=lambda: gitService.reset_to_commit(commit_hash, mode),
                on_success=on_success,
                progress_title='请稍候',
                progress_content=f'正在回滚到 {commit_hash[:7]}...',
                parent=self.window()
            )


class HistoryInterface(QWidget):
    """历史界面 - 提交历史展示（右侧固定，左侧无限滚动）"""

    # 分页加载配置
    PAGE_SIZE = 30  # 每次从Git获取的数量
    LOAD_THRESHOLD = 200  # 滚动到底部阈值（像素）
    CACHE_SIZE = 200  # LRU缓存大小（缓存200条提交记录）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historyInterface")
        self._loaded_count = 0  # 已加载到界面的数量
        self._is_loading = False  # 是否正在加载
        self._has_more = True  # 是否还有更多数据
        self._is_searching = False  # 是否处于搜索模式
        self._search_query = ""  # 当前搜索关键词
        self._commit_cache = {}  # 提交记录缓存 {(count, skip): commits}
        self._cache_hits = 0  # 缓存命中次数
        self._cache_misses = 0  # 缓存未命中次数
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # 主布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)

        # 顶部：标题和操作栏
        self._create_header(layout)

        # 主内容区（使用Fluent Splitter分割左右）
        splitter = Splitter(Qt.Orientation.Horizontal, self)

        # 左侧：带独立滚动的时间线
        left_widget = self._create_timeline_panel()
        splitter.addWidget(left_widget)

        # 右侧：固定的提交详情面板
        self.detailPanel = CommitDetailPanel(self)
        self.detailPanel.setMinimumWidth(350)
        self.detailPanel.setMaximumWidth(450)
        splitter.addWidget(self.detailPanel)

        splitter.setSizes([600, 400])
        splitter.setStretchFactor(0, 1)  # 左侧可伸缩
        splitter.setStretchFactor(1, 0)  # 右侧固定宽度

        layout.addWidget(splitter, 1)

        StyleSheet.SETTING_INTERFACE.apply(self)

    def _create_header(self, parent_layout: QVBoxLayout):
        """创建顶部区域"""
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        self.titleLabel = SubtitleLabel("提交历史", self)
        header_layout.addWidget(self.titleLabel)

        header_layout.addStretch()
        
        # Reflog按钮
        reflog_btn = TransparentPushButton("引用日志 (Reflog)", self, FluentIcon.HISTORY)
        reflog_btn.setToolTip("查看所有操作记录，恢复丢失的提交")
        reflog_btn.installEventFilter(ToolTipFilter(reflog_btn, 500, ToolTipPosition.TOP))
        reflog_btn.clicked.connect(self._on_open_reflog)
        header_layout.addWidget(reflog_btn)

        # 搜索框
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索提交...")
        self.searchEdit.setFixedWidth(200)
        self.searchEdit.textChanged.connect(self._on_search)
        header_layout.addWidget(self.searchEdit)

        parent_layout.addWidget(header)

        # "有更新"提示按钮（初始隐藏）- 药丸形状、居中显示
        hint_layout = QHBoxLayout()
        hint_layout.addStretch()
        
        self.updateHintBtn = PrimaryPushButton("↑ 有新提交", self)
        self.updateHintBtn.setFixedSize(120, 32)  # 限制宽度
        self.updateHintBtn.setStyleSheet("""
            PrimaryPushButton {
                border-radius: 16px;  /* 药丸形状 */
                padding: 4px 16px;
            }
        """)
        self.updateHintBtn.clicked.connect(self._on_update_hint_clicked)
        self.updateHintBtn.hide()
        hint_layout.addWidget(self.updateHintBtn)
        
        hint_layout.addStretch()
        parent_layout.addLayout(hint_layout)

    def _create_timeline_panel(self) -> QWidget:
        """创建时间线面板（独立滚动）"""
        # 使用SmoothScrollArea实现平滑滚动
        self.timelineScroll = SmoothScrollArea(self)
        self.timelineScroll.setWidgetResizable(True)
        self.timelineScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.timelineScroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.timelineScroll.setObjectName("timelineScroll")

        # 设置透明背景
        self.timelineScroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        # 滚动容器
        scroll_container = QWidget()
        scroll_container.setObjectName("timelineContainer")
        scroll_container.setStyleSheet("QWidget#timelineContainer { background: transparent; }")
        scroll_layout = QVBoxLayout(scroll_container)
        scroll_layout.setContentsMargins(0, 0, 8, 0)
        scroll_layout.setSpacing(0)

        # 时间线Widget
        self.timeLine = TimeLineWidget(scroll_container)
        scroll_layout.addWidget(self.timeLine)

        self.timelineScroll.setWidget(scroll_container)

        # 监听滚动事件，实现滚动到底部加载更多
        self.timelineScroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        return self.timelineScroll

    def _connect_signals(self):
        """连接信号"""
        gitService.statusChanged.connect(self._on_status_changed)

    def _on_status_changed(self):
        """Git状态变化时显示更新提示"""
        # 如果还没有加载过任何内容，直接刷新
        if self._loaded_count == 0:
            self.refresh_history()
        else:
            # 显示"有更新"按钮
            self.updateHintBtn.show()

    def _on_update_hint_clicked(self):
        """点击更新提示按钮"""
        self.updateHintBtn.hide()
        # 滚动到顶部
        self.timelineScroll.verticalScrollBar().setValue(0)
        # 刷新
        self.refresh_history()

    def _on_scroll(self, value: int):
        """滚动事件处理 - 滚动到底部加载更多"""
        if self._is_loading or not self._has_more:
            return

        scrollbar = self.timelineScroll.verticalScrollBar()
        max_val = scrollbar.maximum()

        # 检查是否滚动到底部附近
        if max_val > 0 and (max_val - value) < self.LOAD_THRESHOLD:
            self._load_more()

    def _load_more(self):
        """从Git加载更多提交记录（真正异步）"""
        if self._is_loading or not self._has_more:
            return

        self._is_loading = True
        skip = self._loaded_count
        
        from app.common.async_helper import SimpleAsyncTask

        def fetch_commits():
            """在子线程执行Git操作"""
            fast_mode = gitService.is_large_repo()
            return gitService.get_log(count=self.PAGE_SIZE, skip=skip, fast_mode=fast_mode)
        
        SimpleAsyncTask.run(fetch_commits, self._on_load_complete)

    def _on_load_complete(self, commits: list):
        """加载完成回调"""
        if not commits:
            self._has_more = False
        else:
            self._append_commits_to_timeline(commits)
            self._loaded_count += len(commits)

            if len(commits) < self.PAGE_SIZE:
                self._has_more = False

        self._is_loading = False

    def refresh_history(self):
        """刷新提交历史（异步，重新加载，清空缓存）"""
        if not gitService.repo_path:
            return
        
        from app.common.async_helper import SimpleAsyncTask

        # 重置状态
        self._loaded_count = 0
        self._is_loading = True  # 标记正在加载
        self._has_more = True
        
        # 清空缓存（强制刷新）
        self._commit_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

        # 清空现有内容
        self.timeLine.clear()
        
        def fetch_log():
            return gitService.get_log(count=self.PAGE_SIZE, skip=0)
        
        def update_ui(commits):
            """在主线程更新UI"""
            self._is_loading = False
            
            # 缓存首批数据
            cache_key = (self.PAGE_SIZE, 0)
            self._commit_cache[cache_key] = commits

            if not commits:
                self.timeLine.addItem(InfoBarIcon.INFORMATION, "暂无提交记录")
                self._has_more = False
                return

            self._append_commits_to_timeline(commits)
            self._loaded_count = len(commits)

            if len(commits) < self.PAGE_SIZE:
                self._has_more = False
        
        SimpleAsyncTask.run(fetch_log, update_ui)


    def _append_commits_to_timeline(self, commits: list):
        """将提交记录追加到时间线"""
        # 按日期分组
        date_groups = {}
        for commit in commits:
            date = commit.date.split(' ')[0]  # 只取日期部分
            if date not in date_groups:
                date_groups[date] = []
            date_groups[date].append(commit)

        # 添加到时间线
        for date, group_commits in date_groups.items():
            cards = []
            for commit in group_commits:
                card = self._create_commit_card(commit)
                cards.append(card)

            self.timeLine.addItem(
                InfoBarIcon.INFORMATION,
                date,
                cards
            )

    def _create_commit_card(self, commit: CommitInfo) -> TimeLineCard:
        """创建提交卡片"""
        # 构建显示文本
        text = f"{commit.message}\n{commit.author} · {commit.short_hash}"
        card = TimeLineCard(text, self, InfoBarIcon.SUCCESS)

        # 点击事件（使用默认参数捕获当前commit值，避免闭包问题）
        card.clicked.connect(lambda checked=False, c=commit: self.detailPanel.set_commit(c))
        
        # 添加右键菜单
        card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, h=commit.hash: self._show_card_context_menu(card, pos, h)
        )

        return card
    
    def _show_card_context_menu(self, card, pos, commit_hash: str):
        """显示卡片右键菜单"""
        from qfluentwidgets import RoundMenu, Action
        menu = RoundMenu(parent=card)
        
        # 查看详情
        detail_action = Action(FluentIcon.INFO, "查看详情")
        detail_action.triggered.connect(lambda: self._on_view_detail(commit_hash))
        menu.addAction(detail_action)
        
        menu.addSeparator()
        
        # 应用提交
        cherry_pick_action = Action(FluentIcon.COPY, "应用此提交 (Cherry-pick)")
        cherry_pick_action.triggered.connect(lambda: self._on_cherry_pick(commit_hash))
        menu.addAction(cherry_pick_action)
        
        menu.exec(card.mapToGlobal(pos))

    def _on_search(self, text: str):
        """搜索提交"""
        text = text.strip()
        self._search_query = text
        
        if not text:
            # 清空搜索，恢复正常显示
            self._is_searching = False
            self.refresh_history()
            return
        
        # 进入搜索模式
        self._is_searching = True
        self._perform_search(text)
    
    def _perform_search(self, query: str):
        """执行搜索（异步）"""
        if not gitService.repo_path:
            return
        
        from app.common.async_helper import AsyncTask
        
        # 清空现有内容
        self.timeLine.clear()
        
        def on_success(commits):
            if not commits:
                self.timeLine.addItem(InfoBarIcon.INFORMATION, "未找到匹配的提交记录")
            else:
                self._append_commits_to_timeline(commits)
            self._has_more = False
        
        # 使用封装的异步工具
        AsyncTask.run(
            func=lambda: gitService.search_commits(query, search_type="all", count=100),
            on_success=on_success,
            progress_title='请稍候',
            progress_content=f'正在搜索提交: {query}',
            success_title='搜索完成',
            success_content=lambda result: f'找到 {len(result)} 个匹配的提交' if result else '未找到匹配的提交',
            parent=self.window()
        )

    def _on_cherry_pick(self, commit_hash: str):
        """处理Cherry-pick操作"""
        box = MessageBox(
            "Cherry-pick确认",
            f"确定要应用提交 {commit_hash[:7]} 到当前分支吗？",
            self.window()
        )
        if box.exec():
            from app.common.async_helper import AsyncTask
            
            def on_success(result):
                success, msg = result
                if success:
                    InfoBar.success("成功", msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
                else:
                    InfoBar.error("失败", msg, parent=self.window(), position=InfoBarPosition.BOTTOM)
            
            AsyncTask.run(
                func=lambda: gitService.cherry_pick(commit_hash),
                on_success=on_success,
                progress_title='请稍候',
                progress_content=f'正在应用提交 {commit_hash[:7]}...',
                parent=self.window()
            )
    
    def _on_view_detail(self, commit_hash: str):
        """查看提交详情"""
        from .commit_detail_dialog import CommitDetailDialog
        dialog = CommitDetailDialog(commit_hash, self.window())
        dialog.exec()
    
    def _on_open_reflog(self):
        """打开引用日志"""
        from .reflog_dialog import ReflogDialog
        dialog = ReflogDialog(self.window())
        dialog.exec()

    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)
        # 首次显示时刷新
        QTimer.singleShot(100, self.refresh_history)
