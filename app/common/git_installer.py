# coding:utf-8
"""
Git安装检测和辅助安装
"""
import os
import sys
import subprocess
import webbrowser
from pathlib import Path

from PySide6.QtWidgets import QMessageBox
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


class GitInstaller:
    """Git安装检测和辅助"""
    
    @staticmethod
    def check_git_installed() -> tuple[bool, str]:
        """检测Git是否安装
        
        Returns:
            (是否安装, 版本信息)
        
        测试模式：
            设置环境变量GITESS_TEST_NO_GIT=1模拟Git未安装
        """
        # 测试模式：模拟Git未安装
        if os.getenv('GITESS_TEST_NO_GIT') == '1':
            return False, "测试模式: 模拟Git未安装"
        
        try:
            result = subprocess.run(
                ['git', '--version'],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                return True, version
            return False, ""
        except FileNotFoundError:
            return False, "Git未安装"
        except Exception as e:
            return False, str(e)
    
    @staticmethod
    def get_download_url() -> str:
        """获取Git下载链接（根据操作系统）"""
        if sys.platform == 'win32':
            # Windows - 官方安装包
            return "https://git-scm.com/download/win"
        elif sys.platform == 'darwin':
            # macOS - Homebrew或官方
            return "https://git-scm.com/download/mac"
        else:
            # Linux - 包管理器
            return "https://git-scm.com/download/linux"
    
    @staticmethod
    def get_install_command() -> str:
        """获取安装命令（根据操作系统）"""
        if sys.platform == 'win32':
            return "下载安装包后双击安装"
        elif sys.platform == 'darwin':
            return "brew install git"
        else:
            # Linux
            if Path('/etc/debian_version').exists():
                return "sudo apt-get install git"
            elif Path('/etc/redhat-release').exists():
                return "sudo yum install git"
            else:
                return "使用系统包管理器安装git"
    
    @staticmethod
    def open_download_page():
        """打开Git下载页面"""
        url = GitInstaller.get_download_url()
        QDesktopServices.openUrl(QUrl(url))
    
    @staticmethod
    def show_install_guide(parent=None) -> bool:
        """显示安装引导对话框
        
        Returns:
            用户是否选择安装
        """
        from qfluentwidgets import MessageBox
        
        install_cmd = GitInstaller.get_install_command()
        
        content = (
            f"Gitess需要Git才能运行。\n\n"
            f"安装方法：\n"
            f"{install_cmd}\n\n"
            f"点击“立即下载”将打开Git官方下载页面。\n"
            f"安装完成后请重启Gitess。"
        )
        
        box = MessageBox("Git未安装", content, parent)
        box.yesButton.setText("立即下载")
        box.cancelButton.setText("稍后安装")
        
        if box.exec():
            GitInstaller.open_download_page()
            return True
        return False
    
    @staticmethod
    def auto_install_git_windows() -> tuple[bool, str]:
        """Windows自动安装Git（使用winget）
        
        Returns:
            (是否成功, 消息)
        """
        if sys.platform != 'win32':
            return False, "仅支持Windows系统"
        
        try:
            # 检测winget是否可用
            result = subprocess.run(
                ['winget', '--version'],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode != 0:
                return False, "winget不可用，请手动安装"
            
            # 使用winget安装Git
            result = subprocess.run(
                ['winget', 'install', '--id', 'Git.Git', '-e', '--source', 'winget'],
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                return True, "Git安装成功，请重启Gitess"
            else:
                return False, result.stderr or "安装失败"
                
        except FileNotFoundError:
            return False, "winget不可用，请手动安装"
        except subprocess.TimeoutExpired:
            return False, "安装超时，请手动安装"
        except Exception as e:
            return False, f"安装失败: {str(e)}"
    
    @staticmethod
    def show_auto_install_dialog(parent=None) -> bool:
        """显示自动安装对话框（仅Windows）
        
        Returns:
            是否开始安装
        """
        from qfluentwidgets import MessageBox
        
        if sys.platform != 'win32':
            # 非Windows系统，显示手动安装引导
            return GitInstaller.show_install_guide(parent)
        
        # Windows系统，提供自动安装选项
        content = (
            "Gitess需要Git才能运行。\n\n"
            "检测到您使用Windows系统，可以：\n"
            "1. 一键自动安装（使用winget）\n"
            "2. 手动下载安装\n\n"
            "选择“自动安装”将使用winget安装Git。\n"
            "选择“手动安装”将打开下载页面。"
        )
        
        box = MessageBox("Git未安装", content, parent)
        box.yesButton.setText("自动安装")
        box.cancelButton.setText("手动安装")
        
        result = box.exec()
        return result  # True=自动安装, False=手动安装


# 全局实例
gitInstaller = GitInstaller()
