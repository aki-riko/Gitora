# coding: utf-8
"""
Gitora 应用设置
"""
from pathlib import Path

# change DEBUG to False if you want to compile the code to exe
DEBUG = "__compiled__" not in globals()


YEAR = 2025
AUTHOR = "aki-riko"
VERSION = "v1.0.4"
APP_NAME = "Gitora"
# 项目地址
HELP_URL = "https://github.com/aki-riko/Gitora"
REPO_URL = "https://github.com/aki-riko/Gitora"
FEEDBACK_URL = "https://github.com/aki-riko/Gitora/issues"
DOC_URL = "https://github.com/aki-riko/Gitora#readme"

# 自动更新:GitHub 仓库 "owner/repo"(用于查 latest release)
UPDATE_REPO = "aki-riko/Gitora"
# 从 release assets 中挑安装包的关键词(安装包名形如 Gitora-Setup-1.0.4.exe)
UPDATE_ASSET_KEYWORD = "Setup"
# 安装包启动参数:走可见安装向导(用户点下一步),由安装包自身 manifest 触发 UAC 提权。
# 不用 /VERYSILENT 全静默——静默+提权在部分 UAC 配置下会卡死;可见向导更稳。
INSTALLER_SILENT_ARGS = ""

# 使用系统用户数据目录
import os
if os.name == 'nt':  # Windows
    CONFIG_FOLDER = Path(os.getenv('LOCALAPPDATA')) / 'Gitora'
else:  # Linux/macOS
    CONFIG_FOLDER = Path.home() / '.config' / 'Gitora'

CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_FOLDER / "config.json"
