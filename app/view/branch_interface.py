# coding:utf-8
"""
分支界面 - 分支管理、切换、创建、删除、合并
对新人友好的分支操作界面
"""
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame
)
from PySide6.QtGui import QColor

from qfluentwidgets import (
    ScrollArea, CardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, TransparentPushButton, SplitPushButton,
    LineEdit, FluentIcon, InfoBar, InfoBarPosition, RoundMenu, Action,
    setFont, IconWidget, TitleLabel, SubtitleLabel, TransparentToolButton,
    MessageBox, Dialog, ToolTipFilter, ToolTipPosition
)

from app.common.git_service import gitService, BranchInfo
from app.common.style_sheet import StyleSheet
from app.common.icon import Icon
from app.common.logger import get_logger

logger = get_logger("BranchInterface")


class BranchCard(CardWidget):
    """分支卡片"""
    checkoutClicked = Signal(str)   # 分支名
    deleteClicked = Signal(str)     # 分支名
    mergeClicked = Signal(str)      # 分支名

    def __init__(self, branch: BranchInfo, parent=None):
        super().__init__(parent)
        self.branch = branch
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 分支图标
        if self.branch.is_current:
            icon = FluentIcon.CHECKBOX
            icon_color = QColor(76, 175, 80)
        elif self.branch.is_remote:
            icon = FluentIcon.CLOUD
            icon_color = QColor(33, 150, 243)
        else:
            icon = Icon.GIT_BRANCH  # Git专用分支图标
            icon_color = QColor(158, 158, 158)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(24, 24)
        layout.addWidget(self.iconWidget)

        # 分支信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setContentsMargins(0, 0, 0, 0)

        # 分支名
        name_layout = QHBoxLayout()
        name_layout.setSpacing(8)

        self.nameLabel = StrongBodyLabel(self.branch.name, self)
        name_layout.addWidget(self.nameLabel)

        if self.branch.is_current:
            current_label = CaptionLabel("当前", self)
            current_label.setTextColor(QColor(76, 175, 80), QColor(76, 175, 80))
            name_layout.addWidget(current_label)

        if self.branch.is_remote:
            remote_label = CaptionLabel("远程", self)
            remote_label.setTextColor(QColor(33, 150, 243), QColor(33, 150, 243))
            name_layout.addWidget(remote_label)

        name_layout.addStretch()
        info_layout.addLayout(name_layout)

        # 追踪信息
        if self.branch.tracking:
            tracking_label = CaptionLabel(f"追踪: {self.branch.tracking}", self)
            info_layout.addWidget(tracking_label)

        layout.addLayout(info_layout, 1)

        # 操作按钮
        if not self.branch.is_current and not self.branch.is_remote:
            # 切换按钮
            self.checkoutBtn = TransparentToolButton(FluentIcon.SYNC, self)
            self.checkoutBtn.setToolTip("切换到此分支")
            self.checkoutBtn.installEventFilter(ToolTipFilter(self.checkoutBtn, 500, ToolTipPosition.TOP))
            self.checkoutBtn.clicked.connect(lambda: self.checkoutClicked.emit(self.branch.name))
            layout.addWidget(self.checkoutBtn)

            # 合并按钮
            self.mergeBtn = TransparentToolButton(Icon.GIT_MERGE, self)
            self.mergeBtn.setToolTip("合并到当前分支")
            self.mergeBtn.installEventFilter(ToolTipFilter(self.mergeBtn, 500, ToolTipPosition.TOP))
            self.mergeBtn.clicked.connect(lambda: self.mergeClicked.emit(self.branch.name))
            layout.addWidget(self.mergeBtn)

            # 删除按钮
            self.deleteBtn = TransparentToolButton(FluentIcon.DELETE, self)
            self.deleteBtn.setToolTip("删除分支")
            self.deleteBtn.installEventFilter(ToolTipFilter(self.deleteBtn, 500, ToolTipPosition.TOP))
            self.deleteBtn.clicked.connect(lambda: self.deleteClicked.emit(self.branch.name))
            layout.addWidget(self.deleteBtn)

        elif self.branch.is_remote:
            # 检出远程分支
            self.checkoutBtn = TransparentToolButton(FluentIcon.DOWNLOAD, self)
            self.checkoutBtn.setToolTip("检出此远程分支")
            self.checkoutBtn.installEventFilter(ToolTipFilter(self.checkoutBtn, 500, ToolTipPosition.TOP))
            self.checkoutBtn.clicked.connect(self._checkout_remote)
            layout.addWidget(self.checkoutBtn)

    def _checkout_remote(self):
        """检出远程分支"""
        # 从 origin/branch-name 提取 branch-name
        branch_name = self.branch.name
        if '/' in branch_name:
            branch_name = branch_name.split('/', 1)[1]

        self.checkoutClicked.emit(branch_name)


class CreateBranchDialog(Dialog):
    """创建分支对话框"""

    def __init__(self, parent=None):
        super().__init__(
            title="创建新分支",
            content="输入新分支的名称",
            parent=parent
        )
        self._setup_content()

    def _setup_content(self):
        # 分支名输入框
        self.branchEdit = LineEdit(self)
        self.branchEdit.setPlaceholderText("如: feature/new-feature")
        self.branchEdit.setClearButtonEnabled(True)

        # 添加到对话框
        self.textLayout.addWidget(self.branchEdit)

    def get_branch_name(self) -> str:
        """获取分支名"""
        return self.branchEdit.text().strip()


class BranchInterface(ScrollArea):
    """分支界面 - 分支管理"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("branchInterface")
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        self.setWidgetResizable(True)

        # 主容器
        self.container = QWidget()
        self.setWidget(self.container)

        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)

        # 顶部：标题和操作栏
        self._create_header(layout)

        # 当前分支信息卡片
        self._create_current_branch_card(layout)

        # 本地分支列表
        self._create_local_branches_section(layout)

        # 远程分支列表
        self._create_remote_branches_section(layout)

        layout.addStretch()

        StyleSheet.SETTING_INTERFACE.apply(self)

    def _create_header(self, parent_layout: QVBoxLayout):
        """创建顶部区域"""
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        self.titleLabel = SubtitleLabel("分支管理 (Branch)", self)
        header_layout.addWidget(self.titleLabel)

        header_layout.addStretch()

        # 新建分支按钮
        self.createBtn = PrimaryPushButton("新建分支", self, FluentIcon.ADD)
        self.createBtn.clicked.connect(self._on_create_branch)
        header_layout.addWidget(self.createBtn)

        # 同步操作 - Split按钮（主操作：刷新，下拉：获取远程）
        self.syncBtn = SplitPushButton("刷新", self, FluentIcon.SYNC)
        self.syncBtn.clicked.connect(self.refresh_branches)
        
        syncMenu = RoundMenu(parent=self)
        syncMenu.addAction(Action(FluentIcon.DOWNLOAD, "获取远程更新 (Fetch)", triggered=self._on_fetch))
        syncMenu.addAction(Action(FluentIcon.DELETE, "清理远程分支 (Prune)", triggered=self._on_prune_remote))
        self.syncBtn.setFlyout(syncMenu)
        
        header_layout.addWidget(self.syncBtn)

        parent_layout.addWidget(header)

    def _create_current_branch_card(self, parent_layout: QVBoxLayout):
        """创建当前分支信息卡片"""
        self.currentBranchCard = CardWidget(self)
        card_layout = QHBoxLayout(self.currentBranchCard)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(16)

        # 图标
        icon = IconWidget(FluentIcon.DEVELOPER_TOOLS, self)
        icon.setFixedSize(32, 32)
        card_layout.addWidget(icon)

        # 信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        self.currentBranchLabel = TitleLabel("当前分支", self)
        info_layout.addWidget(self.currentBranchLabel)

        self.currentBranchName = StrongBodyLabel("-", self)
        setFont(self.currentBranchName, 16)
        info_layout.addWidget(self.currentBranchName)

        card_layout.addLayout(info_layout, 1)

        parent_layout.addWidget(self.currentBranchCard)

    def _create_local_branches_section(self, parent_layout: QVBoxLayout):
        """创建本地分支区域"""
        # 标题
        title_layout = QHBoxLayout()
        local_title = StrongBodyLabel("本地分支", self)
        title_layout.addWidget(local_title)
        title_layout.addStretch()
        parent_layout.addLayout(title_layout)

        # 分支列表容器
        self.localBranchWidget = QWidget()
        self.localBranchLayout = QVBoxLayout(self.localBranchWidget)
        self.localBranchLayout.setContentsMargins(0, 0, 0, 0)
        self.localBranchLayout.setSpacing(8)

        parent_layout.addWidget(self.localBranchWidget)

    def _create_remote_branches_section(self, parent_layout: QVBoxLayout):
        """创建远程分支区域"""
        # 标题
        title_layout = QHBoxLayout()
        remote_title = StrongBodyLabel("远程分支", self)
        title_layout.addWidget(remote_title)
        title_layout.addStretch()
        parent_layout.addLayout(title_layout)

        # 分支列表容器
        self.remoteBranchWidget = QWidget()
        self.remoteBranchLayout = QVBoxLayout(self.remoteBranchWidget)
        self.remoteBranchLayout.setContentsMargins(0, 0, 0, 0)
        self.remoteBranchLayout.setSpacing(8)

        parent_layout.addWidget(self.remoteBranchWidget)

    def _connect_signals(self):
        """连接信号"""
        gitService.statusChanged.connect(self.refresh_branches)

    def refresh_branches(self):
        """刷新分支列表（完全异步）"""
        if not gitService.repo_path:
            return
        
        from app.common.async_helper import SimpleAsyncTask
        
        def fetch_data():
            """在子线程获取所有数据"""
            current_branch = gitService.get_current_branch()
            branches = gitService.get_branches()
            return current_branch, branches
        
        def update_ui(result):
            """在主线程更新UI"""
            current_branch, branches = result
            
            # 更新当前分支
            self.currentBranchName.setText(current_branch or "-")
            
            # 清空现有列表
            self._clear_layout(self.localBranchLayout)
            self._clear_layout(self.remoteBranchLayout)

            # 分类添加分支
            for branch in branches:
                card = BranchCard(branch, self)
                card.checkoutClicked.connect(self._on_checkout)
                card.deleteClicked.connect(self._on_delete)
                card.mergeClicked.connect(self._on_merge)

                if branch.is_remote:
                    self.remoteBranchLayout.addWidget(card)
                else:
                    self.localBranchLayout.addWidget(card)
        
        SimpleAsyncTask.run(fetch_data, update_ui)

    def _clear_layout(self, layout: QVBoxLayout):
        """清空布局"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_create_branch(self):
        """创建新分支"""
        dialog = CreateBranchDialog(self.window())
        if dialog.exec():
            branch_name = dialog.get_branch_name()
            if not branch_name:
                InfoBar.warning(
                    title="提示",
                    content="请输入分支名称",
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=2000
                )
                return

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
                else:
                    InfoBar.error(
                        title="失败",
                        content=msg,
                        parent=self.window(),
                        position=InfoBarPosition.BOTTOM,
                        duration=3000
                    )
            
            AsyncTask.run(
                func=lambda: gitService.create_branch(branch_name),
                on_success=on_success,
                progress_title='请稍候',
                progress_content=f'正在创建分支: {branch_name}',
                parent=self.window()
            )

    def _on_checkout(self, branch: str):
        """切换分支（异步）"""
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
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=3000
                )
        
        AsyncTask.run(
            func=lambda: gitService.checkout_branch(branch),
            on_success=on_success,
            progress_title='请稍候',
            progress_content=f'正在切换到分支: {branch}',
            parent=self.window()
        )

    def _on_delete(self, branch: str):
        """删除分支"""
        box = MessageBox(
            "确认删除",
            f"确定要删除分支 {branch} 吗？",
            self.window()
        )
        if box.exec():
            from app.common.async_helper import SimpleAsyncTask
            
            def on_finished(result):
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
                    # 尝试强制删除
                    force_box = MessageBox(
                        "删除失败",
                        f"{msg}\n\n是否强制删除？（可能丢失未合并的提交）",
                        self.window()
                    )
                    if force_box.exec():
                        SimpleAsyncTask.run(
                            lambda: gitService.delete_branch(branch, force=True),
                            lambda r: InfoBar.success("成功", r[1], parent=self.window(), position=InfoBarPosition.BOTTOM) if r[0] else InfoBar.error("失败", r[1], parent=self.window(), position=InfoBarPosition.BOTTOM)
                        )
            
            SimpleAsyncTask.run(lambda: gitService.delete_branch(branch), on_finished)

    def _on_merge(self, branch: str):
        """合并分支（异步）"""
        current = gitService.get_current_branch()
        box = MessageBox(
            "确认合并",
            f"确定要将分支 {branch} 合并到当前分支 {current} 吗？",
            self.window()
        )
        if box.exec():
            # 异步执行，会自动显示进度环（通过operationStarted/Finished信号）
            gitService.merge_branch(branch)

    def _on_fetch(self):
        """获取远程更新"""
        gitService.fetch()
    
    def _on_prune_remote(self):
        """清理远程分支引用（异步）"""
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
                self.refresh_branches()
            else:
                InfoBar.error(
                    title="失败",
                    content=msg,
                    parent=self.window(),
                    position=InfoBarPosition.BOTTOM,
                    duration=3000
                )
        
        AsyncTask.run(
            func=gitService.prune_remote,
            on_success=on_success,
            progress_title='请稍候',
            progress_content='正在清理远程分支引用...',
            parent=self.window()
        )

    def showEvent(self, event):
        """显示事件"""
        super().showEvent(event)
        # 首次显示时刷新
        QTimer.singleShot(100, self.refresh_branches)
