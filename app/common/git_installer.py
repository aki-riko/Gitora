# coding:utf-8
"""
Git 安装检测和辅助(跨平台:Windows / macOS / Linux)。

QML 版只用到检测与下载页跳转;旧 QWidget 时代的 qfluentwidgets 对话框/winget
自动安装已移除(QML 版不调用,且 qfluentwidgets 不再是依赖)。
"""
import os
import sys
import subprocess
from pathlib import Path

from .logger import get_logger

logger = get_logger("GitInstaller")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


class GitInstaller:
    """Git 安装检测和辅助(纯跨平台,无 GUI 框架依赖)"""

    @staticmethod
    def check_git_installed() -> tuple[bool, str]:
        """检测 Git 是否安装。

        Returns:
            (是否安装, 版本信息)

        测试模式:设环境变量 GITESS_TEST_NO_GIT=1 模拟 Git 未安装。
        """
        logger.info("检查Git安装状态")
        if os.getenv('GITESS_TEST_NO_GIT') == '1':
            return False, "测试模式: 模拟Git未安装"

        try:
            result = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                text=True,
                timeout=5,
                # CREATE_NO_WINDOW 仅 Windows 有(防弹控制台窗口);其它平台传 0
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                logger.info(f"Git已安装: {version}")
                return True, version
            logger.warning("Git命令执行失败")
            return False, ""
        except FileNotFoundError:
            logger.warning("Git未安装")
            return False, "Git未安装"
        except Exception as e:
            logger.exception(f"Git检测异常: {e}")
            return False, str(e)

    @staticmethod
    def get_download_url() -> str:
        """获取 Git 下载链接(按操作系统)"""
        if sys.platform == 'win32':
            return "https://git-scm.com/download/win"
        elif sys.platform == 'darwin':
            return "https://git-scm.com/download/mac"
        else:
            return "https://git-scm.com/download/linux"

    @staticmethod
    def get_install_command() -> str:
        """获取安装命令提示(按操作系统)"""
        if sys.platform == 'win32':
            return "下载安装包后双击安装"
        elif sys.platform == 'darwin':
            return "brew install git(或安装 Xcode Command Line Tools)"
        else:
            if Path('/etc/debian_version').exists():
                return "sudo apt-get install git"
            elif Path('/etc/redhat-release').exists():
                return "sudo yum install git"
            else:
                return "使用系统包管理器安装 git"

    @staticmethod
    def open_download_page():
        """用系统浏览器打开 Git 下载页面"""
        url = GitInstaller.get_download_url()
        QDesktopServices.openUrl(QUrl(url))


# 全局实例
gitInstaller = GitInstaller()
