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
    StepProgressBar, TimeLineWidget, TimeLineCard, Splitter
)

from app.common.git_service import gitService, FileChange, FileStatus
from app.common.style_sheet import StyleSheet
from app.common.icon import Icon
from app.view.virtual_file_list import VirtualFileList


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
        self.setFixedHeight(64)  # 统一卡片高度
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

    def _get_status_icon(self):
        """根据状态返回图标"""
        icon_map = {
            FileStatus.MODIFIED: FluentIcon.EDIT,
            FileStatus.ADDED: FluentIcon.ADD_TO,
            FileStatus.DELETED: FluentIcon.DELETE,
            FileStatus.UNTRACKED: FluentIcon.DOCUMENT,
            FileStatus.RENAMED: FluentIcon.SYNC,  # 暂时保持
            FileStatus.UNMERGED: Icon.GIT_CLOSE_PR,  # 使用Git专用冲突图标
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
        history_action = Action(FluentIcon.HISTORY, "文件历史 (History)")
        history_action.triggered.connect(self._on_view_history)
        menu.addAction(history_action)
        
        # 查看代码作者
        blame_action = Action(FluentIcon.PEOPLE, "代码作者 (Blame)")
        blame_action.triggered.connect(self._on_view_blame)
        menu.addAction(blame_action)
        
        menu.exec(self.mapToGlobal(pos))
    
    def _on_view_history(self):
        """查看文件历史"""
        from .file_history_dialog import FileHistoryDialog
        dialog = FileHistoryDialog(self.file_change.path, self.window())
        dialog.exec()
    
    def _on_view_blame(self):
        """查看代码作者（异步）"""
        from app.common.async_helper import AsyncTask
        
        AsyncTask.run(
            func=lambda: gitService.blame(self.file_change.path),
            progress_title='请稍候',
            progress_content=f'正在分析代码作者: {self.file_change.path}',
            success_title='分析完成',
            success_content=lambda result: f'共 {len(result)} 行代码' if result else 'Blame信息获取失败',
            parent=self.window()
        )


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
        """显示文件差异（异步）"""
        self._current_file = file_path
        self._is_staged = is_staged
        self.filePathLabel.setText(file_path)
        
        # 显示加载提示
        self.diffEdit.hide()
        self.emptyLabel.setText("正在加载diff...")
        self.emptyLabel.show()
        
        # 异步获取diff
        from app.common.async_helper import SimpleAsyncTask
        
        def fetch_diff():
            return gitService.get_diff(file_path, is_staged)
        
        def on_finished(diff_text):
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
        
        SimpleAsyncTask.run(fetch_diff, on_finished)
    
    def _format_diff(self, diff_text: str):
        """格式化并高亮diff文本"""
        self.diffEdit.clear()
        
        # 主题感知颜色
        is_dark = isDarkTheme()
        default_color = QColor(255, 255, 255) if is_dark else QColor(0, 0, 0)
        
        # 按行处理
        lines = diff_text.split('\n')
        for line in lines:
            if line.startswith('+') and not line.startswith('+++'):
                # 新增行 - 绿色
                self.diffEdit.setTextColor(QColor(76, 175, 80) if is_dark else QColor(34, 139, 34))
                self.diffEdit.append(line)
            elif line.startswith('-') and not line.startswith('---'):
                # 删除行 - 红色
                self.diffEdit.setTextColor(QColor(244, 67, 54) if is_dark else QColor(220, 53, 69))
                self.diffEdit.append(line)
            elif line.startswith('@@'):
                # 位置标记 - 蓝色
                self.diffEdit.setTextColor(QColor(66, 165, 245) if is_dark else QColor(33, 150, 243))
                self.diffEdit.append(line)
            elif line.startswith('diff') or line.startswith('index') or \
                 line.startswith('---') or line.startswith('+++'):
                # 文件头 - 灰色
                self.diffEdit.setTextColor(QColor(158, 158, 158))
                self.diffEdit.append(line)
            else:
                # 普通行 - 主题感知颜色
                self.diffEdit.setTextColor(default_color)
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

        self.commitBtn = PrimaryPushButton("提交", self, Icon.GIT_COMMIT)  # Git专用提交图标
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
                position=InfoBarPosition.BOTTOM_RIGHT,
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
                position=InfoBarPosition.BOTTOM_RIGHT,
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
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=2000
            )
        else:
            InfoBar.error(
                title="失败",
                content=msg,
                parent=self.window(),
                position=InfoBarPosition.BOTTOM_RIGHT,
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
        splitter = Splitter(Qt.Orientation.Horizontal, self)

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
        self.repoPathLabel.setMaximumWidth(500)  # 限制最大宽度
        from PySide6.QtCore import Qt
        self.repoPathLabel.setTextFormat(Qt.TextFormat.PlainText)
        # 启用文本省略
        from PySide6.QtWidgets import QSizePolicy
        self.repoPathLabel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        path_branch_layout.addWidget(self.repoPathLabel, 0)
        self.branchLabel = CaptionLabel("", self)
        path_branch_layout.addWidget(self.branchLabel, 0)
        path_branch_layout.addStretch(1)
        repo_info_layout.addLayout(path_branch_layout)
        
        header_layout.addLayout(repo_info_layout, 0)
        header_layout.addStretch(1)

        # === 工具栏按钮组 ===
        # 使用分隔线和间距优化视觉分组
        
        # 第一组：仓库操作
        self.repoBtn = SplitPushButton("打开仓库", self, FluentIcon.FOLDER)
        self.repoBtn.clicked.connect(self._open_repo)
        repoMenu = RoundMenu(parent=self)
        repoMenu.addAction(Action(FluentIcon.FOLDER, "打开本地仓库", triggered=self._open_repo))
        repoMenu.addAction(Action(FluentIcon.DOWNLOAD, "克隆远程仓库", triggered=self._on_clone_repo))
        repoMenu.addAction(Action(FluentIcon.ADD, "初始化新仓库", triggered=self._on_init_repo))
        repoMenu.addSeparator()
        self.recentMenu = RoundMenu("最近仓库", repoMenu)
        self.recentMenu.setIcon(FluentIcon.HISTORY)
        repoMenu.addMenu(self.recentMenu)
        self._update_recent_repos_menu()
        self.repoBtn.setFlyout(repoMenu)
        header_layout.addWidget(self.repoBtn)
        
        # 分隔线 1
        self._add_separator(header_layout)
        
        # 第二组：临时保存
        stash_btn = TransparentToolButton(Icon.GIT_PR_DRAFT, self)
        stash_btn.setToolTip("临时保存 (Stash)")
        stash_btn.installEventFilter(ToolTipFilter(stash_btn, 500, ToolTipPosition.TOP))
        stash_btn.clicked.connect(self._on_open_stash)
        header_layout.addWidget(stash_btn)
        
        # 分隔线 2
        self._add_separator(header_layout)
        
        # 第三组：同步操作（重点）
        self.syncBtn = SplitPushButton("同步", self, FluentIcon.SYNC)
        self.syncBtn.clicked.connect(self._on_pull)
        syncMenu = RoundMenu(parent=self)
        syncMenu.addAction(Action(Icon.GIT_PULL_REQUEST, "拉取 (Pull)", triggered=self._on_pull))
        syncMenu.addAction(Action(Icon.GIT_PULL_REQUEST, "拉取并变基 (Rebase)", triggered=self._on_pull_rebase))
        syncMenu.addSeparator()
        syncMenu.addAction(Action(FluentIcon.SEND, "推送 (Push)", triggered=self._on_push))
        syncMenu.addAction(Action(FluentIcon.CANCEL, "强制推送 (Force)", triggered=self._on_force_push))
        self.syncBtn.setFlyout(syncMenu)
        header_layout.addWidget(self.syncBtn)
        
        # 分隔线 3
        self._add_separator(header_layout)
        
        # 第四组：远程仓库
        remote_btn = TransparentToolButton(FluentIcon.CLOUD, self)
        remote_btn.setToolTip("远程仓库 (Remote)")
        remote_btn.installEventFilter(ToolTipFilter(remote_btn, 500, ToolTipPosition.TOP))
        remote_btn.clicked.connect(self._on_manage_remotes)
        header_layout.addWidget(remote_btn)

        parent_layout.addWidget(header)
    
    def _add_separator(self, layout: QHBoxLayout):
        """添加工具栏分隔线"""
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setFixedHeight(20)
        # 设置颜色（根据主题自动调整）
        if isDarkTheme():
            separator.setStyleSheet("QFrame { color: rgba(255, 255, 255, 0.08); }")
        else:
            separator.setStyleSheet("QFrame { color: rgba(0, 0, 0, 0.08); }")
        layout.addWidget(separator)

    def _create_file_list_panel(self) -> QWidget:
        """创建文件变更列表面板（上下分割：文件列表+差异显示）"""
        # 使用Fluent垂直分割器
        splitter = Splitter(Qt.Orientation.Vertical, self)
        
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

        # 虚拟滚动文件列表
        self.fileList = VirtualFileList(self)
        self.fileList.stageClicked.connect(self._on_stage_file)
        self.fileList.discardClicked.connect(self._on_discard_file)
        self.fileList.fileSelected.connect(self._on_file_selected)
        layout.addWidget(self.fileList, 1)
        
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
        gitService.progressUpdated.connect(self._on_progress_updated)  # 仅用于一键操作进度条

    def _update_recent_repos_menu(self):
        """更新最近仓库菜单"""
        from app.common.recent_repos import recentReposManager
        
        self.recentMenu.clear()
        recent_repos = recentReposManager.get_all()
        
        if not recent_repos:
            empty_action = Action(FluentIcon.INFO, "暂无最近仓库")
            empty_action.setEnabled(False)
            self.recentMenu.addAction(empty_action)
        else:
            for repo_path in recent_repos:
                import os
                repo_name = os.path.basename(repo_path)
                action = Action(FluentIcon.FOLDER, f"{repo_name}")
                action.triggered.connect(lambda checked=False, p=repo_path: self._open_recent_repo(p))
                self.recentMenu.addAction(action)
            
            self.recentMenu.addSeparator()
            clear_action = Action(FluentIcon.DELETE, "清空列表")
            clear_action.triggered.connect(self._clear_recent_repos)
            self.recentMenu.addAction(clear_action)
    
    def _open_recent_repo(self, path: str):
        """打开最近的仓库"""
        if gitService.set_repo_path(path):
            import os
            repo_name = os.path.basename(path)
            self.repoNameLabel.setText(repo_name)
            # 设置路径，并添加Tooltip显示完整路径
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QFontMetrics
            metrics = QFontMetrics(self.repoPathLabel.font())
            elided_path = metrics.elidedText(path, Qt.TextElideMode.ElideMiddle, 480)
            self.repoPathLabel.setText(elided_path)
            self.repoPathLabel.setToolTip(path)
            self.refresh_status()
            InfoBar.success(
                title="成功",
                content=f"已打开仓库: {repo_name}",
                parent=self.window(),
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=2000
            )
        else:
            InfoBar.error(
                title="错误",
                content="仓库不存在或已被删除",
                parent=self.window(),
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=3000
            )
    
    def _clear_recent_repos(self):
        """清空最近仓库列表"""
        from app.common.recent_repos import recentReposManager
        recentReposManager.clear()
        self._update_recent_repos_menu()
        InfoBar.success(
            title="成功",
            content="已清空最近仓库列表",
            parent=self.window(),
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2000
        )
    
    def _on_init_repo(self):
        """初始化新仓库（异步）"""
        path = QFileDialog.getExistingDirectory(
            self,
            "选择要初始化的目录",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if not path:
            return
        
        from app.common.async_helper import SimpleAsyncTask
        from app.common.recent_repos import recentReposManager
        from qfluentwidgetspro import ProgressInfoBar
        import os
        
        # 显示进度环
        progress_bar = ProgressInfoBar.create(
            title='请稍候',
            content='正在初始化Git仓库...',
            orient=Qt.Orientation.Horizontal,
            isClosable=False,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self.window()
        )
        
        def on_finished(result):
            success, msg = result
            if success:
                progress_bar.setTitle('成功')
                progress_bar.setContent(msg)
                progress_bar.success(duration=2000)
                
                # set_repo_path会触发statusChanged信号，自动刷新所有界面
                if gitService.set_repo_path(path):
                    repo_name = os.path.basename(path)
                    self.repoNameLabel.setText(repo_name)
                    # 设置路径，并添加Tooltip显示完整路径
                    from PySide6.QtCore import Qt
                    from PySide6.QtGui import QFontMetrics
                    metrics = QFontMetrics(self.repoPathLabel.font())
                    elided_path = metrics.elidedText(path, Qt.TextElideMode.ElideMiddle, 480)
                    self.repoPathLabel.setText(elided_path)
                    self.repoPathLabel.setToolTip(path)
                    recentReposManager.add(path)
                    self._update_recent_repos_menu()
                    
                    # 显示引导窗口
                    self._show_init_guide(path)
            else:
                progress_bar.setTitle('失败')
                progress_bar.setContent(msg)
                progress_bar.error(duration=3000)
        
        SimpleAsyncTask.run(lambda: gitService.init(path), on_finished)
    
    def _show_init_guide(self, path: str):
        """显示初始化仓库引导窗口"""
        from .init_repo_guide import InitRepoGuide
        
        # 延迟显示引导窗口，等待进度条关闭
        def show_guide():
            self._guide_window = InitRepoGuide(path)  # GuideWindow不需要parent参数
            self._guide_window.completed.connect(self._on_init_guide_completed)
            self._guide_window.show()
        
        QTimer.singleShot(2500, show_guide)
    
    def _on_init_guide_completed(self, repo_path: str):
        """引导完成"""
        InfoBar.success(
            title="配置完成",
            content="Git仓库已初始化并完成配置！",
            parent=self.window(),
            position=InfoBarPosition.BOTTOM_RIGHT,
            duration=2000
        )
    
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
                from PySide6.QtCore import QThread
                from qfluentwidgetspro import ProgressInfoBar
                from app.common.recent_repos import recentReposManager
                
                repo_name = os.path.basename(path)
                self.repoNameLabel.setText(repo_name)
                # 设置路径，并添加Tooltip显示完整路径
                from PySide6.QtCore import Qt
                from PySide6.QtGui import QFontMetrics
                metrics = QFontMetrics(self.repoPathLabel.font())
                elided_path = metrics.elidedText(path, Qt.TextElideMode.ElideMiddle, 480)
                self.repoPathLabel.setText(elided_path)
                self.repoPathLabel.setToolTip(path)
                # set_repo_path已触发statusChanged信号，自动刷新所有界面
                
                # 添加到最近仓库列表
                recentReposManager.add(path)
                self._update_recent_repos_menu()
                
                # 显示进度条
                progress_bar = ProgressInfoBar.create(
                    title='请稍候',
                    content='正在检测仓库大小...',
                    orient=Qt.Orientation.Horizontal,
                    isClosable=False,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    parent=self.window()
                )
                
                # 异步检测大仓库
                class CheckRepoWorker(QThread):
                    finished = Signal(bool, dict)
                    
                    def run(self):
                        is_large = gitService.is_large_repo()
                        repo_info = gitService.get_repo_size() if is_large else {}
                        self.finished.emit(is_large, repo_info)
                
                def on_check_finished(is_large, repo_info):
                    if is_large:
                        progress_bar.setTitle('大仓库检测')
                        progress_bar.setContent(f"检测到大仓库（{repo_info.get('commit_count', 0)}个提交）")
                        progress_bar.warning(duration=3000)
                    else:
                        progress_bar.setTitle('成功')
                        progress_bar.setContent('已打开仓库')
                        progress_bar.success(duration=2000)
                
                self._check_worker = CheckRepoWorker()  # 保存引用
                self._check_worker.finished.connect(on_check_finished)
                self._check_worker.start()
            else:
                InfoBar.error(
                    title="错误",
                    content="所选目录不是有效的Git仓库",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000
                )

    def refresh_status(self):
        """刷新状态（异步）"""
        if not gitService.repo_path:
            return
        
        from app.common.async_helper import SimpleAsyncTask
        
        def fetch_data():
            """在子线程获取数据"""
            branch = gitService.get_current_branch()
            changes = gitService.get_status()
            return branch, changes
        
        def update_ui(result):
            """在主线程更新UI"""
            branch, changes = result
            
            # 更新分支信息
            self.branchLabel.setText(f"分支: {branch}" if branch else "")
            
            # 更新文件变更计数
            self.changesLabel.setText(f"文件变更 ({len(changes)})")
            
            # 使用虚拟滚动列表显示所有文件
            self.fileList.setFileChanges(changes)
        
        SimpleAsyncTask.run(fetch_data, update_ui)

    def _on_stage_file(self, path: str, stage: bool):
        """暂存/取消暂存文件（异步）"""
        from app.common.async_helper import SimpleAsyncTask
        
        def do_stage():
            if stage:
                return gitService.stage_file(path)
            else:
                return gitService.unstage_file(path)
        
        def on_finished(success):
            if not success:
                InfoBar.error(
                    title="错误",
                    content=f"操作失败: {path}",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
        
        SimpleAsyncTask.run(do_stage, on_finished)

    def _on_discard_file(self, path: str):
        """放弃文件修改"""
        box = MessageBox(
            "确认放弃修改",
            f"确定要放弃对 {path} 的修改吗？此操作不可恢复。",
            self.window()
        )
        if box.exec():
            from app.common.async_helper import SimpleAsyncTask
            
            def on_finished(success):
                if success:
                    InfoBar.success(
                        title="成功",
                        content="已放弃修改",
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM_RIGHT,
                        duration=2000
                    )
                else:
                    InfoBar.error(
                        title="错误",
                        content="放弃修改失败",
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM_RIGHT,
                        duration=2000
                    )
            
            SimpleAsyncTask.run(lambda: gitService.discard_file(path), on_finished)

    def _on_file_selected(self, path: str, is_staged: bool = False):
        """文件被选中 - 显示文件差异"""
        if path:
            self.diffViewPanel.show_diff(path, is_staged)
        else:
            self.diffViewPanel.clear_diff()

    def _stage_all(self):
        """暂存所有（异步）"""
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            if result:
                InfoBar.success(
                    title="成功",
                    content="已暂存所有变更",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
            else:
                InfoBar.error(
                    title="失败",
                    content="暂存失败",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
        
        AsyncTask.run(
            func=gitService.stage_all,
            on_success=on_success,
            progress_title='请稍候',
            progress_content='正在暂存所有文件...',
            parent=self.window()
        )

    def _unstage_all(self):
        """取消暂存所有（异步）"""
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            if result:
                InfoBar.success(
                    title="成功",
                    content="已取消暂存所有文件",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
            else:
                InfoBar.error(
                    title="失败",
                    content="取消暂存失败",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
        
        AsyncTask.run(
            func=gitService.unstage_all,
            on_success=on_success,
            progress_title='请稍候',
            progress_content='正在取消暂存...',
            parent=self.window()
        )
    
    def _on_commit(self, message: str):
        """提交（异步）"""
        from app.common.async_helper import AsyncTask
        
        def on_success(result):
            success, msg = result
            if success:
                self.commitPanel.clear()
                InfoBar.success(
                    title="成功",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000
                )
        
        AsyncTask.run(
            func=lambda: gitService.commit(message),
            on_success=on_success,
            progress_title='请稍候',
            progress_content='正在提交...',
            parent=self.window()
        )
    
    def _on_clone_repo(self):
        """克隆仓库"""
        from .clone_dialog import CloneDialog
        dialog = CloneDialog(self.window())
        if dialog.exec():
            url, path = dialog.get_clone_info()
            if not url or not path:
                InfoBar.warning(
                    title="提示",
                    content="请输入URL和路径",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000
                )
                return
            
            # 异步克隆
            def on_clone_finished(success: bool, msg: str):
                if success:
                    # 克隆成功后自动打开仓库
                    if gitService.set_repo_path(path):
                        import os
                        repo_name = os.path.basename(path)
                        self.repoNameLabel.setText(repo_name)
                        # 设置路径，并添加Tooltip显示完整路径
                        from PySide6.QtCore import Qt
                        from PySide6.QtGui import QFontMetrics
                        metrics = QFontMetrics(self.repoPathLabel.font())
                        elided_path = metrics.elidedText(path, Qt.TextElideMode.ElideMiddle, 480)
                        self.repoPathLabel.setText(elided_path)
                        self.repoPathLabel.setToolTip(path)
                        self.refresh_status()
            
            gitService.clone(url, path, on_clone_finished)
    
    def _on_open_stash(self):
        """打开Stash管理对话框"""
        from .stash_dialog import StashDialog
        dialog = StashDialog(self.window())
        dialog.exec()

    def _on_pull(self):
        """拉取"""
        gitService.pull()
    
    def _on_pull_rebase(self):
        """拉取并Rebase"""
        gitService.pull(rebase=True)

    def _on_push(self):
        """推送"""
        # 先检查远程仓库配置
        remotes = gitService.get_remote_info()
        if not remotes:
            # 无远程仓库，显示配置向导
            self._show_remote_config_guide()
            return
        
        gitService.push()
    
    def _on_force_push(self):
        """强制推送（危险操作）"""
        from app.common.danger_dialog import DangerOperationDialog
        
        if DangerOperationDialog.confirm_force_push(self.window()):
            gitService.push(force=True)

    def _on_quick_commit_push(self, message: str):
        """一键提交推送"""
        self.quickPanel.quickBtn.setEnabled(False)
        gitService.quick_commit_push(message, self._on_quick_finished)

    def _on_quick_finished(self, success: bool, msg: str):
        """一键操作完成"""
        self.quickPanel.quickBtn.setEnabled(True)
        if success:
            self.quickPanel.reset()

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
    
    def _show_remote_config_guide(self):
        """显示远程仓库配置向导"""
        from app.view.remote_config_wizard import RemoteConfigWizard
        
        wizard = RemoteConfigWizard(self.window())
        wizard.configCompleted.connect(self.refresh_status)
        wizard.show()
    
    def _on_manage_remotes(self):
        """管理远程仓库"""
        if not gitService.repo_path:
            InfoBar.warning(
                '提示',
                '请先打开一个Git仓库',
                duration=2000,
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT
            )
            return
        
        # 异步获取远程仓库信息
        from app.common.async_helper import AsyncTask
        
        def on_success(remotes):
            if not remotes:
                # 无远程仓库，显示配置向导
                box = MessageBox(
                    '远程仓库列表',
                    '当前仓库没有配置远程仓库\n\n是否现在配置？',
                    self.window()
                )
                if box.exec():
                    self._show_remote_config_guide()
            else:
                # 显示远程仓库列表
                content = "\n".join([f"{name}: {url}" for name, url in remotes])
                content += "\n\n点击确定打开配置向导"
                
                box = MessageBox(
                    '远程仓库列表',
                    content,
                    self.window()
                )
                if box.exec():
                    self._show_remote_config_guide()
        
        AsyncTask.run(
            func=gitService.get_remote_info,
            on_success=on_success,
            progress_title='请稍候',
            progress_content='正在获取远程仓库信息...',
            parent=self
        )
