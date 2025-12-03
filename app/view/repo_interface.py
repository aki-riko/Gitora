# coding:utf-8
"""
仓库界面 - 文件变更、暂存、提交、一键操作
对新人友好的Git操作界面
"""
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame,
    QFileDialog, QSplitter, QStackedWidget, QTextEdit
)
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, SplitPushButton,
    TextEdit, LineEdit, FluentIcon, InfoBar, InfoBarPosition,
    CheckBox, Action, setFont, IconWidget, RoundMenu,
    ToolTipFilter, ToolTipPosition, isDarkTheme, TitleLabel,
    SubtitleLabel, TransparentToolButton, MessageBox
)
from qfluentwidgetspro import (
    StepProgressBar, TimeLineWidget, TimeLineCard
)

from app.common.git_service import gitService, FileChange, FileStatus
from app.common.style_sheet import StyleSheet


class FileChangeCard(CardWidget):
    """文件变更卡片"""
    stageClicked = Signal(str, bool)     # 文件路径, 是否暂存
    discardClicked = Signal(str)         # 文件路径
    selected = Signal(str)               # 文件路径

    def __init__(self, file_change: FileChange, parent=None):
        super().__init__(parent)
        self.file_change = file_change
        self._setup_ui()
        
        # 启用右键菜单
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _setup_ui(self):
        self.setFixedHeight(60)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # 复选框（用于批量选择）
        self.checkbox = CheckBox(self)
        self.checkbox.setChecked(False)
        layout.addWidget(self.checkbox)

        # 状态图标
        self.statusIcon = IconWidget(self._get_status_icon(), self)
        self.statusIcon.setFixedSize(20, 20)
        layout.addWidget(self.statusIcon)

        # 文件信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(0, 0, 0, 0)

        self.pathLabel = BodyLabel(self.file_change.path, self)
        self.pathLabel.setObjectName("pathLabel")
        info_layout.addWidget(self.pathLabel)

        status_text = self.file_change.status_text
        if self.file_change.staged:
            status_text += " (已暂存)"
        self.statusLabel = CaptionLabel(status_text, self)
        self.statusLabel.setObjectName("statusLabel")
        self.statusLabel.setTextColor(self._get_status_color(), self._get_status_color())
        info_layout.addWidget(self.statusLabel)

        layout.addLayout(info_layout, 1)

        # 操作按钮
        if self.file_change.staged:
            # 已暂存 -> 取消暂存
            self.actionBtn = TransparentToolButton(FluentIcon.REMOVE, self)
            self.actionBtn.setToolTip("取消暂存")
            self.actionBtn.installEventFilter(ToolTipFilter(self.actionBtn, 500, ToolTipPosition.TOP))
            self.actionBtn.clicked.connect(lambda: self.stageClicked.emit(self.file_change.path, False))
        else:
            # 未暂存 -> 暂存
            self.actionBtn = TransparentToolButton(FluentIcon.ADD, self)
            self.actionBtn.setToolTip("暂存")
            self.actionBtn.installEventFilter(ToolTipFilter(self.actionBtn, 500, ToolTipPosition.TOP))
            self.actionBtn.clicked.connect(lambda: self.stageClicked.emit(self.file_change.path, True))

        layout.addWidget(self.actionBtn)

        # 放弃修改按钮
        if not self.file_change.staged:
            self.discardBtn = TransparentToolButton(FluentIcon.DELETE, self)
            self.discardBtn.setToolTip("放弃修改")
            self.discardBtn.installEventFilter(ToolTipFilter(self.discardBtn, 500, ToolTipPosition.TOP))
            self.discardBtn.clicked.connect(lambda: self.discardClicked.emit(self.file_change.path))
            layout.addWidget(self.discardBtn)

        # 点击事件
        self.clicked.connect(lambda: self.selected.emit(self.file_change.path))

    def _get_status_icon(self) -> FluentIcon:
        """根据状态返回图标"""
        icon_map = {
            FileStatus.MODIFIED: FluentIcon.EDIT,
            FileStatus.ADDED: FluentIcon.ADD_TO,
            FileStatus.DELETED: FluentIcon.DELETE,
            FileStatus.UNTRACKED: FluentIcon.DOCUMENT,
            FileStatus.RENAMED: FluentIcon.SYNC,
            FileStatus.UNMERGED: FluentIcon.CANCEL,
        }
        return icon_map.get(self.file_change.status, FluentIcon.DOCUMENT)

    def _get_status_color(self) -> QColor:
        """根据状态返回颜色"""
        if self.file_change.staged:
            return QColor(76, 175, 80)  # 绿色
        color_map = {
            FileStatus.MODIFIED: QColor(255, 152, 0),   # 橙色
            FileStatus.ADDED: QColor(76, 175, 80),       # 绿色
            FileStatus.DELETED: QColor(244, 67, 54),     # 红色
            FileStatus.UNTRACKED: QColor(158, 158, 158), # 灰色
            FileStatus.UNMERGED: QColor(244, 67, 54),    # 红色
        }
        return color_map.get(self.file_change.status, QColor(158, 158, 158))
    
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        menu = RoundMenu(parent=self)
        
        # 查看历史
        history_action = Action(FluentIcon.HISTORY, "查看文件历史")
        history_action.triggered.connect(self._on_view_history)
        menu.addAction(history_action)
        
        menu.exec(self.mapToGlobal(pos))
    
    def _on_view_history(self):
        """查看文件历史"""
        from .file_history_dialog import FileHistoryDialog
        dialog = FileHistoryDialog(self.file_change.path, self.window())
        dialog.exec()


class DiffViewPanel(QFrame):
    """文件差异显示面板"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._current_file = None
        self._is_staged = False
    
    def _setup_ui(self):
        self.setObjectName("diffViewPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        
        # 标题栏
        title_layout = QHBoxLayout()
        self.titleLabel = StrongBodyLabel("文件差异", self)
        title_layout.addWidget(self.titleLabel)
        title_layout.addStretch()
        
        self.filePathLabel = CaptionLabel("", self)
        title_layout.addWidget(self.filePathLabel)
        layout.addLayout(title_layout)
        
        # Diff显示区域
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
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.diffEdit, 1)
        
        # 空状态提示
        self.emptyLabel = BodyLabel("选择一个文件查看差异", self)
        self.emptyLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.emptyLabel)
        
        # 初始显示空状态
        self.diffEdit.hide()
        self.emptyLabel.show()
    
    def show_diff(self, file_path: str, is_staged: bool):
        """显示文件差异"""
        self._current_file = file_path
        self._is_staged = is_staged
        self.filePathLabel.setText(file_path)
        
        # 获取diff
        diff_text = gitService.get_diff(file_path, is_staged)
        
        if not diff_text or not diff_text.strip():
            # 无差异
            self.diffEdit.hide()
            self.emptyLabel.setText(f"无差异: {file_path}")
            self.emptyLabel.show()
        else:
            # 显示diff
            self.emptyLabel.hide()
            self.diffEdit.show()
            self._format_diff(diff_text)
    
    def _format_diff(self, diff_text: str):
        """格式化并高亮diff文本"""
        self.diffEdit.clear()
        
        # 按行处理
        lines = diff_text.split('\n')
        for line in lines:
            if line.startswith('+') and not line.startswith('+++'):
                # 新增行 - 绿色
                self.diffEdit.setTextColor(QColor(34, 139, 34))
                self.diffEdit.append(line)
            elif line.startswith('-') and not line.startswith('---'):
                # 删除行 - 红色
                self.diffEdit.setTextColor(QColor(220, 53, 69))
                self.diffEdit.append(line)
            elif line.startswith('@@'):
                # 位置标记 - 蓝色
                self.diffEdit.setTextColor(QColor(33, 150, 243))
                self.diffEdit.append(line)
            elif line.startswith('diff') or line.startswith('index') or \
                 line.startswith('---') or line.startswith('+++'):
                # 文件头 - 灰色
                self.diffEdit.setTextColor(QColor(128, 128, 128))
                self.diffEdit.append(line)
            else:
                # 普通行 - 默认颜色
                self.diffEdit.setTextColor(QColor(0, 0, 0))
                self.diffEdit.append(line)
    
    def clear_diff(self):
        """清空差异显示"""
        self._current_file = None
        self._is_staged = False
        self.filePathLabel.setText("")
        self.diffEdit.clear()
        self.diffEdit.hide()
        self.emptyLabel.setText("选择一个文件查看差异")
        self.emptyLabel.show()


class CommitPanel(QFrame):
    """提交面板"""
    commitRequested = Signal(str)  # 提交信息

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("commitPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 标题
        self.titleLabel = StrongBodyLabel("提交信息", self)
        layout.addWidget(self.titleLabel)

        # 提交信息输入框
        self.messageEdit = TextEdit(self)
        self.messageEdit.setPlaceholderText("请输入提交信息...\n\n提示：第一行为标题，空一行后为详细描述")
        self.messageEdit.setMinimumHeight(100)
        layout.addWidget(self.messageEdit)

        # 提交按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)

        self.commitBtn = PrimaryPushButton("提交", self, FluentIcon.ACCEPT)
        self.commitBtn.clicked.connect(self._on_commit)
        btn_layout.addWidget(self.commitBtn)

        self.amendBtn = PushButton("修改上次提交", self)
        self.amendBtn.setToolTip("修改最后一次提交的信息或内容\n⚠️ 如已推送到远程，需要强制推送")
        self.amendBtn.installEventFilter(ToolTipFilter(self.amendBtn, 500, ToolTipPosition.TOP))
        self.amendBtn.clicked.connect(self._on_amend)
        btn_layout.addWidget(self.amendBtn)

        layout.addLayout(btn_layout)

    def _on_commit(self):
        message = self.messageEdit.toPlainText().strip()
        if not message:
            InfoBar.warning(
                title="提示",
                content="请输入提交信息",
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )
            return
        self.commitRequested.emit(message)

    def _on_amend(self):
        message = self.messageEdit.toPlainText().strip()
        if not message:
            InfoBar.warning(
                title="提示",
                content="请输入提交信息",
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )
            return

        success, msg = gitService.amend_commit(message)
        if success:
            self.messageEdit.clear()
            InfoBar.success(
                title="成功",
                content=msg,
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )
        else:
            InfoBar.error(
                title="失败",
                content=msg,
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=3000
            )

    def clear(self):
        self.messageEdit.clear()


class QuickActionPanel(QFrame):
    """一键操作面板 - 对新人友好"""
    quickCommitPush = Signal(str)  # 提交信息

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setObjectName("quickActionPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题
        title_layout = QHBoxLayout()
        self.iconWidget = IconWidget(FluentIcon.SPEED_HIGH, self)
        self.iconWidget.setFixedSize(28, 28)
        title_layout.addWidget(self.iconWidget)

        self.titleLabel = TitleLabel("一键提交推送", self)
        title_layout.addWidget(self.titleLabel)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 说明
        self.descLabel = BodyLabel(
            "新手推荐！自动执行：暂存所有变更 → 提交 → 推送到远程",
            self
        )
        self.descLabel.setWordWrap(True)
        layout.addWidget(self.descLabel)

        # 进度条
        self.stepBar = StepProgressBar(self)
        self.stepBar.addStep("暂存", FluentIcon.ADD_TO)
        self.stepBar.addStep("提交", FluentIcon.ACCEPT)
        self.stepBar.addStep("推送", FluentIcon.SEND)
        self.stepBar.setCurrentStep(-1)  # 初始无进度
        layout.addWidget(self.stepBar, 0, Qt.AlignmentFlag.AlignCenter)

        # 提交信息
        self.messageEdit = LineEdit(self)
        self.messageEdit.setPlaceholderText("输入提交信息，如：修复登录bug")
        self.messageEdit.setClearButtonEnabled(True)
        layout.addWidget(self.messageEdit)

        # 一键按钮
        self.quickBtn = PrimaryPushButton("一键提交推送", self, FluentIcon.SEND)
        self.quickBtn.setFixedHeight(44)
        setFont(self.quickBtn, 14)
        self.quickBtn.clicked.connect(self._on_quick_action)
        layout.addWidget(self.quickBtn)

        layout.addStretch()

    def _on_quick_action(self):
        from datetime import datetime
        message = self.messageEdit.text().strip()
        if not message:
            # 使用默认提交信息
            message = f"更新 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            self.messageEdit.setText(message)
        self.quickCommitPush.emit(message)

    def set_progress(self, step: int):
        """设置进度 0=暂存, 1=提交, 2=推送"""
        self.stepBar.setCurrentStep(step)

    def reset(self):
        """重置状态"""
        self.stepBar.setCurrentStep(-1)
        self.messageEdit.clear()


class RepoInterface(ScrollArea):
    """仓库界面 - 主界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("repoInterface")
        self._setup_ui()
        self._connect_signals()

        # 定时刷新状态
        self.refreshTimer = QTimer(self)
        self.refreshTimer.timeout.connect(self.refresh_status)
        self.refreshTimer.start(3000)  # 每3秒刷新

    def _setup_ui(self):
        self.setWidgetResizable(True)

        # 主容器
        self.container = QWidget()
        self.setWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)

        # 顶部：仓库信息和操作栏
        self._create_header(layout)

        # 主内容区：左右分栏
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # 左侧：文件变更列表
        left_widget = self._create_file_list_panel()
        splitter.addWidget(left_widget)

        # 右侧：提交面板 + 一键操作
        right_widget = self._create_action_panel()
        splitter.addWidget(right_widget)

        splitter.setSizes([500, 400])
        layout.addWidget(splitter, 1)

        StyleSheet.SETTING_INTERFACE.apply(self)

    def _create_header(self, parent_layout: QVBoxLayout):
        """创建顶部区域"""
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # 仓库信息（左侧垂直布局）
        repo_info_layout = QVBoxLayout()
        repo_info_layout.setSpacing(2)
        
        # 仓库名称（大标题）
        self.repoNameLabel = SubtitleLabel("未选择仓库", self)
        repo_info_layout.addWidget(self.repoNameLabel)
        
        # 仓库路径 + 分支（小字）
        path_branch_layout = QHBoxLayout()
        path_branch_layout.setSpacing(8)
        self.repoPathLabel = CaptionLabel("", self)
        path_branch_layout.addWidget(self.repoPathLabel)
        self.branchLabel = CaptionLabel("", self)
        path_branch_layout.addWidget(self.branchLabel)
        path_branch_layout.addStretch()
        repo_info_layout.addLayout(path_branch_layout)
        
        header_layout.addLayout(repo_info_layout)
        header_layout.addStretch()

        # 打开仓库按钮
        self.openRepoBtn = PushButton("打开仓库", self, FluentIcon.FOLDER)
        self.openRepoBtn.clicked.connect(self._open_repo)
        header_layout.addWidget(self.openRepoBtn)

        # Stash按钮
        stash_btn = TransparentPushButton("暂存管理", self, FluentIcon.SAVE)
        stash_btn.setToolTip("Stash管理 - 暂存和恢复工作区变更")
        stash_btn.installEventFilter(ToolTipFilter(stash_btn, 500, ToolTipPosition.TOP))
        stash_btn.clicked.connect(self._on_open_stash)
        header_layout.addWidget(stash_btn)

        # 同步按钮（拉取/推送）
        self.syncBtn = SplitPushButton("同步", self, FluentIcon.SYNC)
        syncMenu = RoundMenu(parent=self)
        syncMenu.addAction(Action(FluentIcon.DOWNLOAD, "拉取", triggered=self._on_pull))
        syncMenu.addAction(Action(FluentIcon.SEND, "推送", triggered=self._on_push))
        self.syncBtn.setFlyout(syncMenu)
        
        header_layout.addWidget(self.syncBtn)

        parent_layout.addWidget(header)

    def _create_file_list_panel(self) -> QWidget:
        """创建文件变更列表面板（上下分割：文件列表+差异显示）"""
        # 使用垂直分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        
        # 上方：文件列表
        file_panel = QFrame()
        file_panel.setObjectName("fileListPanel")
        layout = QVBoxLayout(file_panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标题和操作
        title_layout = QHBoxLayout()
        self.changesLabel = StrongBodyLabel("文件变更 (0)", self)
        title_layout.addWidget(self.changesLabel)
        title_layout.addStretch()

        self.stageAllBtn = TransparentPushButton("全部暂存", self, FluentIcon.ADD)
        self.stageAllBtn.clicked.connect(self._stage_all)
        title_layout.addWidget(self.stageAllBtn)

        self.unstageAllBtn = TransparentPushButton("全部取消", self, FluentIcon.REMOVE)
        self.unstageAllBtn.clicked.connect(self._unstage_all)
        title_layout.addWidget(self.unstageAllBtn)

        layout.addLayout(title_layout)

        # 文件列表容器
        self.fileListWidget = QWidget()
        self.fileListLayout = QVBoxLayout(self.fileListWidget)
        self.fileListLayout.setContentsMargins(0, 0, 0, 0)
        self.fileListLayout.setSpacing(8)
        self.fileListLayout.addStretch()

        # 滚动区域
        file_scroll = ScrollArea()
        file_scroll.setWidgetResizable(True)
        file_scroll.setWidget(self.fileListWidget)
        file_scroll.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(file_scroll, 1)
        
        splitter.addWidget(file_panel)

        # 下方：差异显示面板
        self.diffViewPanel = DiffViewPanel(self)
        splitter.addWidget(self.diffViewPanel)
        
        # 设置默认大小比例（文件列表:差异显示 = 3:2）
        splitter.setSizes([300, 200])

        return splitter

    def _create_action_panel(self) -> QWidget:
        """创建右侧操作面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 一键操作面板（推荐给新手）
        self.quickPanel = QuickActionPanel(self)
        self.quickPanel.quickCommitPush.connect(self._on_quick_commit_push)
        layout.addWidget(self.quickPanel)

        # 提交面板
        self.commitPanel = CommitPanel(self)
        self.commitPanel.commitRequested.connect(self._on_commit)
        layout.addWidget(self.commitPanel)

        layout.addStretch()

        return panel

    def _connect_signals(self):
        """连接信号"""
        gitService.statusChanged.connect(self.refresh_status)
        gitService.operationStarted.connect(self._on_operation_started)
        gitService.operationFinished.connect(self._on_operation_finished)
        gitService.progressUpdated.connect(self._on_progress_updated)

    def _open_repo(self):
        """打开仓库"""
        path = QFileDialog.getExistingDirectory(
            self,
            "选择Git仓库",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if path:
            if gitService.set_repo_path(path):
                import os
                repo_name = os.path.basename(path)
                self.repoNameLabel.setText(repo_name)
                self.repoPathLabel.setText(path)
                self.refresh_status()
                InfoBar.success(
                    title="成功",
                    content="已打开仓库",
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                    duration=2000
                )
            else:
                InfoBar.error(
                    title="错误",
                    content="所选目录不是有效的Git仓库",
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                    duration=3000
                )

    def refresh_status(self):
        """刷新状态"""
        if not gitService.repo_path:
            return

        # 更新分支信息
        branch = gitService.get_current_branch()
        self.branchLabel.setText(f"分支: {branch}" if branch else "")

        # 获取文件变更
        changes = gitService.get_status()
        self.changesLabel.setText(f"文件变更 ({len(changes)})")

        # 清空现有列表
        while self.fileListLayout.count() > 1:
            item = self.fileListLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 添加文件卡片
        for change in changes:
            card = FileChangeCard(change, self)
            card.stageClicked.connect(self._on_stage_file)
            card.discardClicked.connect(self._on_discard_file)
            card.selected.connect(self._on_file_selected)
            self.fileListLayout.insertWidget(self.fileListLayout.count() - 1, card)

    def _on_stage_file(self, path: str, stage: bool):
        """暂存/取消暂存文件"""
        if stage:
            success = gitService.stage_file(path)
        else:
            success = gitService.unstage_file(path)

        if not success:
            InfoBar.error(
                title="错误",
                content=f"操作失败: {path}",
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )

    def _on_discard_file(self, path: str):
        """放弃文件修改"""
        box = MessageBox(
            "确认放弃修改",
            f"确定要放弃对 {path} 的修改吗？此操作不可恢复。",
            self.window()
        )
        if box.exec():
            success = gitService.discard_file(path)
            if success:
                InfoBar.success(
                    title="成功",
                    content="已放弃修改",
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                    duration=2000
                )
            else:
                InfoBar.error(
                    title="错误",
                    content="放弃修改失败",
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                    duration=2000
                )

    def _on_file_selected(self, path: str):
        """文件被选中 - 显示文件差异"""
        # 查找文件状态
        changes = gitService.get_status()
        file_change = next((c for c in changes if c.path == path), None)
        
        if file_change:
            # 显示差异（根据是否暂存选择显示暂存区或工作区差异）
            self.diffViewPanel.show_diff(path, file_change.staged)
        else:
            # 文件未找到
            self.diffViewPanel.clear_diff()

    def _stage_all(self):
        """暂存所有"""
        if gitService.stage_all():
            InfoBar.success(
                title="成功",
                content="已暂存所有变更",
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )

    def _unstage_all(self):
        """取消暂存所有"""
        if gitService.unstage_all():
            InfoBar.success(
                title="成功",
                content="已取消暂存所有文件",
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )

    def _on_commit(self, message: str):
        """提交"""
        success, msg = gitService.commit(message)
        if success:
            self.commitPanel.clear()
            InfoBar.success(
                title="成功",
                content=msg,
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )
        else:
            InfoBar.error(
                title="失败",
                content=msg,
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=3000
            )

    def _on_open_stash(self):
        """打开Stash管理对话框"""
        from .stash_dialog import StashDialog
        dialog = StashDialog(self.window())
        dialog.exec()

    def _on_pull(self):
        """拉取"""
        gitService.pull()

    def _on_push(self):
        """推送"""
        gitService.push()

    def _on_quick_commit_push(self, message: str):
        """一键提交推送"""
        self.quickPanel.quickBtn.setEnabled(False)
        gitService.quick_commit_push(message, self._on_quick_finished)

    def _on_quick_finished(self, success: bool, msg: str):
        """一键操作完成"""
        self.quickPanel.quickBtn.setEnabled(True)
        if success:
            self.quickPanel.reset()

    def _on_operation_started(self, msg: str):
        """操作开始"""
        InfoBar.info(
            title="进行中",
            content=msg,
            parent=self.window(),
            position=InfoBarPosition.TOP,
            duration=1500
        )

    def _on_operation_finished(self, success: bool, msg: str):
        """操作完成"""
        if success:
            InfoBar.success(
                title="成功",
                content=msg,
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=2000
            )
        else:
            InfoBar.error(
                title="失败",
                content=msg,
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=3000
            )

    def _on_progress_updated(self, percent: int, msg: str):
        """进度更新"""
        # 更新一键操作进度条
        if percent < 33:
            self.quickPanel.set_progress(0)
        elif percent < 66:
            self.quickPanel.set_progress(1)
        elif percent < 100:
            self.quickPanel.set_progress(2)
        else:
            self.quickPanel.set_progress(2)
