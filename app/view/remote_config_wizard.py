# coding:utf-8
"""
远程仓库配置向导
复用 RemoteInterface 组件，使用必填模式
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout

from qfluentwidgets import (
    TitleLabel, BodyLabel, setFont, ComboBox, 
    InfoBar, InfoBarPosition, TextEdit, LineEdit
)
from qfluentwidgetspro import GuideWindow

from ..common.git_service import gitService
from .init_repo_guide import RemoteInterface
from ..common.logger import get_logger

logger = get_logger("RemoteConfigWizard")


class WelcomeStep(QWidget):
    """欢迎界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(28)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 标题
        self.titleLabel = TitleLabel("远程仓库配置向导", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel, 0, Qt.AlignmentFlag.AlignCenter)
        
        # 说明
        self.bodyLabel = BodyLabel(
            "检测到您的仓库远程信息不完整或需要配置。\n\n"
            "本向导将引导您完成：\n"
            "• 🌐 配置远程仓库URL\n"
            "• 🔗 设置分支跟踪关系\n"
            "• ✅ 验证远程连接\n\n"
            "⚠️ 注意：所有步骤必须完整填写才能继续",
            self
        )
        self.bodyLabel.setWordWrap(True)
        self.bodyLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.bodyLabel, 0, Qt.AlignmentFlag.AlignCenter)


class BranchConfigStep(QWidget):
    """分支配置步骤"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("配置分支跟踪", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "设置本地分支与远程分支的跟踪关系，用于推送和拉取",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        
        layout.addSpacing(20)
        
        # 本地分支
        self.localBranchLabel = BodyLabel("本地分支: *", self)
        layout.addWidget(self.localBranchLabel)
        
        self.localBranchCombo = ComboBox(self)
        layout.addWidget(self.localBranchCombo)
        
        # 加载本地分支列表
        branches = gitService.get_branches()
        if branches:
            # 提取分支名称字符串列表
            branch_names = [b.name for b in branches if not b.is_remote]
            if branch_names:
                self.localBranchCombo.addItems(branch_names)
                current = gitService.get_current_branch()
                if current and current in branch_names:
                    self.localBranchCombo.setCurrentText(current)
        
        layout.addSpacing(12)
        
        # 远程分支
        self.remoteBranchLabel = BodyLabel("远程分支: *", self)
        layout.addWidget(self.remoteBranchLabel)
        
        # 使用LineEdit而不是ComboBox，因为QFluentWidgets的ComboBox不支持setEditable
        self.remoteBranchEdit = LineEdit(self)
        self.remoteBranchEdit.setPlaceholderText("请输入远程分支名称，如：main、master")
        
        # 智能检测远程分支：优先使用当前分支，其次是 master，最后是 main
        default_remote_branch = "main"  # 默认值
        current_branch = gitService.get_current_branch()
        if current_branch:
            # 使用当前分支名作为默认远程分支
            default_remote_branch = current_branch
            logger.info(f"使用当前分支作为默认远程分支: {default_remote_branch}")
        else:
            # 如果没有当前分支，检查是否有 master 分支
            branches = gitService.get_branches()
            local_branch_names = [b.name for b in branches if not b.is_remote]
            if 'master' in local_branch_names:
                default_remote_branch = "master"
                logger.info("检测到 master 分支，使用 master 作为默认远程分支")
            else:
                logger.info("使用 main 作为默认远程分支")
        
        self.remoteBranchEdit.setText(default_remote_branch)
        layout.addWidget(self.remoteBranchEdit)
        
        layout.addStretch()
        
        # 所有控件创建完成后，再连接信号
        self.localBranchCombo.currentTextChanged.connect(self._validate_inputs)
        self.remoteBranchEdit.textChanged.connect(self._validate_inputs)
        
        # 初始验证
        self._validate_inputs()
    
    def _validate_inputs(self):
        """实时验证"""
        local = self.localBranchCombo.currentText().strip()
        remote = self.remoteBranchEdit.text().strip()
        return bool(local and remote)
    
    def get_branch_config(self) -> tuple[str, str]:
        """获取分支配置"""
        return (
            self.localBranchCombo.currentText().strip(),
            self.remoteBranchEdit.text().strip()
        )
    
    def is_valid(self) -> bool:
        """验证是否有效"""
        local, remote = self.get_branch_config()
        return bool(local and remote)


class ConfirmationStep(QWidget):
    """确认配置步骤"""
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 标题
        self.titleLabel = TitleLabel("确认配置", self)
        setFont(self.titleLabel, 28, QFont.Weight.Bold)
        layout.addWidget(self.titleLabel)
        
        # 说明
        self.hintLabel = BodyLabel(
            "请确认以下配置信息，点击'完成'将执行配置",
            self
        )
        self.hintLabel.setWordWrap(True)
        self.hintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.hintLabel)
        
        layout.addSpacing(20)
        
        # 配置预览
        self.configPreview = TextEdit(self)
        self.configPreview.setReadOnly(True)
        self.configPreview.setFixedHeight(200)
        layout.addWidget(self.configPreview)
        
        # 提示
        self.confirmHintLabel = BodyLabel(
            "✅ 点击'完成'将执行以下操作：\n"
            "• 添加/更新远程仓库URL\n"
            "• 设置分支跟踪关系\n"
            "• 尝试连接远程仓库验证配置\n\n"
            "⚠️ 如果远程仓库需要认证，请确保已配置SSH密钥或凭据",
            self
        )
        self.confirmHintLabel.setWordWrap(True)
        self.confirmHintLabel.setTextColor(QColor(100, 100, 100), QColor(216, 216, 216))
        layout.addWidget(self.confirmHintLabel)
        
        layout.addStretch()
    
    def set_config_preview(self, remote_name: str, remote_url: str, 
                          local_branch: str, remote_branch: str):
        """设置配置预览"""
        preview_text = (
            "远程仓库配置\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"【远程仓库】\n"
            f"名称: {remote_name}\n"
            f"URL: {remote_url}\n\n"
            f"【分支跟踪】\n"
            f"本地分支: {local_branch}\n"
            f"远程分支: {remote_name}/{remote_branch}\n\n"
            f"【Git命令等效】\n"
            f"git remote add {remote_name} {remote_url}\n"
            f"git branch --set-upstream-to={remote_name}/{remote_branch} {local_branch}"
        )
        self.configPreview.setPlainText(preview_text)


class RemoteConfigWizard(GuideWindow):
    """远程仓库配置向导（复用组件版本）"""
    
    configCompleted = Signal()  # 配置完成信号
    
    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle("远程仓库配置向导")
        self.resize(800, 500)
        
        # 获取已存在的远程列表
        self.existing_remotes = []
        self.existing_remote_url = None
        remotes = gitService.get_remote_info()
        if remotes:
            self.existing_remotes = [name for name, _ in remotes]
            # 如果存在 origin，获取其 URL
            for name, url in remotes:
                if name == 'origin':
                    self.existing_remote_url = url
                    logger.info(f"检测到已有远程仓库: {name} -> {url}")
                    break
        
        # 创建步骤页面
        self.welcomePage = WelcomeStep()
        self.remoteInfoPage = RemoteInterface(existing_remotes=self.existing_remotes)  # 始终必填
        self.branchConfigPage = BranchConfigStep()
        self.confirmationPage = ConfirmationStep()
        
        # 如果存在已有远程仓库，自动填充
        if self.existing_remote_url:
            self._auto_fill_remote_info(self.existing_remote_url)
        
        # 添加页面
        self.addPage(self.welcomePage)
        self.addPage(self.remoteInfoPage)
        self.addPage(self.branchConfigPage)
        self.addPage(self.confirmationPage)
        
        # 连接信号
        self.appStarted.connect(self._on_finish)
        self.currentIndexChanged.connect(self._on_page_changed)
        
        # 连接验证信号来实时控制按钮状态
        self.remoteInfoPage.nameEdit.textChanged.connect(self._update_next_button)
        self.remoteInfoPage.hostEdit.textChanged.connect(self._update_next_button)
        self.remoteInfoPage.userEdit.textChanged.connect(self._update_next_button)
        self.remoteInfoPage.repoEdit.textChanged.connect(self._update_next_button)
        self.branchConfigPage.localBranchCombo.currentTextChanged.connect(self._update_next_button)
        self.branchConfigPage.remoteBranchEdit.textChanged.connect(self._update_next_button)
        
        # 初始化按钮状态
        self._update_next_button()
    
    def _auto_fill_remote_info(self, url: str):
        """自动填充远程仓库信息
        
        Args:
            url: 远程仓库URL，支持 HTTPS 和 SSH 格式
        """
        import re
        
        logger.info(f"开始解析远程仓库URL: {url}")
        
        # 解析 SSH 格式
        # ssh://git@host:port/user/repo.git
        ssh_pattern_full = r'^ssh://([^@]+)@([^:]+):(\d+)/(.+)/([^/]+?)(?:\.git)?$'
        # git@host:user/repo.git
        ssh_pattern_short = r'^([^@]+)@([^:]+):(.+)/([^/]+?)(?:\.git)?$'
        # 解析 HTTPS 格式: https://github.com/user/repo.git
        https_pattern = r'^https?://([^/]+)/(.+?)/(.+?)(?:\.git)?$'
        
        protocol = None
        host = None
        port = None
        user = None
        repo = None
        
        # 尝试匹配 SSH 完整格式: ssh://git@host:port/user/repo.git
        match = re.match(ssh_pattern_full, url)
        if match:
            protocol = 'git'
            ssh_user = match.group(1)  # git
            host = match.group(2)
            port = match.group(3)
            user = match.group(4)
            repo = match.group(5)
            logger.info(f"SSH完整格式解析: host={host}, port={port}, user={user}, repo={repo}")
        else:
            # 尝试匹配 SSH 简写格式: git@host:user/repo.git
            match = re.match(ssh_pattern_short, url)
            if match:
                protocol = 'git'
                ssh_user = match.group(1)  # git
                host = match.group(2)
                port = '22'  # 默认端口
                path = match.group(3)
                repo = match.group(4)
                # 从路径中提取用户名（取最后一个/之前的部分）
                path_parts = path.split('/')
                if len(path_parts) >= 1:
                    user = path_parts[-1] if len(path_parts) == 1 else '/'.join(path_parts[:-1]) if len(path_parts) > 1 else path_parts[0]
                else:
                    user = path
                logger.info(f"SSH简写格式解析: host={host}, port={port}, user={user}, repo={repo}")
            else:
                # 尝试匹配 HTTPS 格式
                match = re.match(https_pattern, url)
                if match:
                    protocol = 'https'
                    host = match.group(1)
                    user = match.group(2)
                    repo = match.group(3)
                    logger.info(f"HTTPS格式解析: host={host}, user={user}, repo={repo}")
        
        # 填充到界面
        if protocol and host and user and repo:
            # 设置协议类型
            self.remoteInfoPage.protocolSegmented.setCurrentItem(protocol)
            self.remoteInfoPage._on_protocol_changed(protocol)
            
            # 填充字段
            self.remoteInfoPage.hostEdit.setText(host)
            self.remoteInfoPage.userEdit.setText(user)
            self.remoteInfoPage.repoEdit.setText(repo)
            
            # 如果是 SSH 且有端口，填充端口
            if protocol == 'git' and port:
                self.remoteInfoPage.sshPortEdit.setText(port)
            
            logger.info("远程仓库信息已自动填充")
            
            # 触发验证
            self.remoteInfoPage._validate_inputs()
        else:
            logger.warning(f"无法解析远程仓库URL: {url}")
    
    def _update_next_button(self):
        """实时更新下一步按钮状态"""
        current_index = self.currentIndex()
        
        # 第1页（欢迎页）：总是启用
        if current_index == 0:
            is_valid = True
        # 第2页：验证远程信息
        elif current_index == 1:
            is_valid = self.remoteInfoPage.is_valid()
        # 第3页：验证分支配置
        elif current_index == 2:
            is_valid = self.branchConfigPage.is_valid()
        # 第4页（确认页）：总是启用
        elif current_index == 3:
            is_valid = True
        else:
            is_valid = True
        
        # 更新按钮状态
        try:
            if hasattr(self, 'nextButton'):
                self.nextButton.setEnabled(is_valid)
            elif hasattr(self, 'nextBtn'):
                self.nextBtn.setEnabled(is_valid)
        except:
            pass
    
    def _on_page_changed(self, index: int):
        """页面切换时验证并更新按钮状态"""
        # 第2页：立即触发验证UI更新
        if index == 1:
            self.remoteInfoPage._validate_inputs()
        # 第3页：立即触发验证UI更新
        elif index == 2:
            self.branchConfigPage._validate_inputs()
        
        # 更新按钮状态
        self._update_next_button()
        
        # 第4页：更新确认页预览
        if index == 3:
            remote_name, remote_url = self.remoteInfoPage.get_remote_info()
            local_branch, remote_branch = self.branchConfigPage.get_branch_config()
            self.confirmationPage.set_config_preview(
                remote_name, remote_url, local_branch, remote_branch
            )
    
    def _on_finish(self):
        """完成配置"""
        # 防止重复点击
        if hasattr(self, '_is_configuring') and self._is_configuring:
            logger.warning("配置正在进行中，忽略重复点击")
            return
        
        self._is_configuring = True
        
        from app.common.async_helper import AsyncTask
        
        # 获取配置信息
        remote_name, remote_url = self.remoteInfoPage.get_remote_info()
        local_branch, remote_branch = self.branchConfigPage.get_branch_config()
        
        def do_config():
            """执行配置操作"""
            # 1. 添加/更新远程仓库
            if remote_name in self.existing_remotes:
                success, msg = gitService.set_remote_url(remote_name, remote_url)
                if not success:
                    raise Exception(f"更新远程URL失败: {msg}")
            else:
                success, msg = gitService.add_remote(remote_name, remote_url)
                if not success:
                    raise Exception(f"添加远程仓库失败: {msg}")
            
            # 2. 先fetch远程分支信息
            success, msg = gitService.fetch_sync(remote=remote_name)
            if not success:
                raise Exception(f"Fetch远程分支失败: {msg}\n\n请检查:\n1. 远程仓库URL是否正确\n2. 网络连接是否正常\n3. SSH密钥或凭据是否配置正确")
            
            # 3. 检查本地分支是否存在，如果不存在则创建
            current_branch = gitService.get_current_branch()
            branches = gitService.get_branches()
            local_branches = [b.name for b in branches if not b.is_remote]
            
            if local_branch not in local_branches:
                # 本地分支不存在，创建并checkout
                success, msg = gitService.create_branch(local_branch, checkout=True)
                if not success:
                    raise Exception(f"创建本地分支失败: {msg}")
            elif current_branch != local_branch:
                # 本地分支存在但不是当前分支，切换过去
                success, msg = gitService.checkout_branch(local_branch)
                if not success:
                    raise Exception(f"切换分支失败: {msg}")
            
            # 4. 检查远程分支是否存在（使用更可靠的方式）
            # 使用 git ls-remote 直接查询远程分支
            success, stdout, stderr = gitService._run_git_sync(['ls-remote', '--heads', remote_name])
            logger.info(f"git ls-remote 结果: success={success}, stdout={repr(stdout)}, stderr={repr(stderr)}")
            
            if not success:
                logger.warning(f"无法查询远程分支: {stderr}")
                # 如果 ls-remote 失败，尝试使用 get_branches
                branches = gitService.get_branches()
                remote_branches = [b.name for b in branches if b.is_remote]
                logger.info(f"使用 get_branches 获取远程分支: {remote_branches}")
            else:
                # 解析 ls-remote 输出
                remote_branches = []
                for line in stdout.strip().split('\n'):
                    if line:
                        # 格式: <hash>\trefs/heads/<branch>
                        parts = line.split('\t')
                        if len(parts) == 2 and parts[1].startswith('refs/heads/'):
                            branch_name = parts[1].replace('refs/heads/', '')
                            remote_branches.append(f"{remote_name}/{branch_name}")
                logger.info(f"解析到的远程分支: {remote_branches}")
            
            target_remote_branch = f"{remote_name}/{remote_branch}"
            
            if target_remote_branch not in remote_branches:
                # 远程分支不存在
                available_branches = [b for b in remote_branches if b.startswith(f"{remote_name}/")]
                if available_branches:
                    # 有其他分支，但目标分支不存在，提示用户
                    branches_str = "\n  - ".join(available_branches)
                    error_msg = (
                        f"远程分支 '{target_remote_branch}' 不存在。\n\n"
                        f"可用的远程分支：\n  - {branches_str}\n\n"
                        f"请返回上一步，选择正确的远程分支名称。"
                    )
                    raise Exception(error_msg)
                else:
                    # 远程仓库是空的（刚创建），这是正常情况
                    # 不设置 upstream，返回特殊标记让用户手动推送创建分支
                    logger.info(f"远程仓库 '{remote_name}' 是空的，需要首次推送创建分支")
                    return "empty_remote"
            
            # 5. 设置分支跟踪（仅当远程分支存在时）
            success, msg = gitService.set_upstream(local_branch, remote_name, remote_branch)
            if not success:
                # 如果还是失败，给出警告
                logger.warning(f"设置上游分支失败: {msg}")
                return "upstream_warning"
            
            return True
        
        def on_success(result):
            """配置成功"""
            # 重置配置状态
            self._is_configuring = False
            
            if result == "empty_remote":
                # 远程仓库是空的，需要首次推送
                InfoBar.success(
                    "配置完成",
                    f"远程仓库 '{remote_name}' 已添加。\n"
                    f"远程仓库为空，请点击「推送」按钮进行首次推送。",
                    parent=self.parent() if self.parent() else self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=5000
                )
            elif result == "upstream_warning":
                # 远程仓库配置成功，但上游分支设置失败
                InfoBar.warning(
                    "配置部分完成",
                    f"远程仓库 '{remote_name}' 已添加，但上游分支设置失败。\n\n"
                    f"请手动运行: git push -u {remote_name} {local_branch}",
                    parent=self.parent() if self.parent() else self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=5000
                )
            else:
                # 完全成功
                InfoBar.success(
                    "配置完成",
                    f"远程仓库 '{remote_name}' 已配置完成",
                    parent=self.parent() if self.parent() else self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000
                )
            self.configCompleted.emit()
            self.close()
        
        def on_error(e):
            """配置失败"""
            # 重置配置状态
            self._is_configuring = False
            
            InfoBar.error(
                "配置失败",
                str(e),
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=5000
            )
        
        AsyncTask.run(
            func=do_config,
            on_success=on_success,
            on_error=on_error,
            progress_title='正在配置',
            progress_content='正在配置远程仓库和分支跟踪关系...',
            parent=self.parent() if self.parent() else self
        )
