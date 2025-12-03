# coding: utf-8
"""
Gitess 应用设置
"""
from pathlib import Path

# change DEBUG to False if you want to compile the code to exe
DEBUG = "__compiled__" not in globals()


YEAR = 2025
AUTHOR = "Gitess"
VERSION = "v1.0.0"
APP_NAME = "Gitess"
HELP_URL = "https://github.com/Gitess/Gitess"
REPO_URL = "https://github.com/Gitess/Gitess"
FEEDBACK_URL = "https://github.com/Gitess/Gitess/issues"
DOC_URL = "https://github.com/Gitess/Gitess/wiki"

# 使用系统用户数据目录
import os
if os.name == 'nt':  # Windows
    CONFIG_FOLDER = Path(os.getenv('LOCALAPPDATA')) / 'Gitess'
else:  # Linux/macOS
    CONFIG_FOLDER = Path.home() / '.config' / 'Gitess'

CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_FOLDER / "config.json"

# QFluentWidgets Pro License（请勿泄露到公开仓库）
# 可以通过环境变量 QFLUENTWIDGETS_PRO_LICENSE 设置
# 或在此处直接配置（但需确保.gitignore已忽略此文件）
PRO_LICENSE = ""  # 留空，将从环境变量或配置文件读取
