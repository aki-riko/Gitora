# coding: utf-8
"""
Gitora 应用设置
"""
from pathlib import Path

# change DEBUG to False if you want to compile the code to exe
DEBUG = "__compiled__" not in globals()


YEAR = 2025
AUTHOR = "aki-riko"
VERSION = "v1.0.3"
APP_NAME = "Gitora"
# 项目地址
HELP_URL = "https://github.com/aki-riko/Gitora"
REPO_URL = "https://github.com/aki-riko/Gitora"
FEEDBACK_URL = "https://github.com/aki-riko/Gitora/issues"
DOC_URL = "https://github.com/aki-riko/Gitora#readme"

# 使用系统用户数据目录
import os
if os.name == 'nt':  # Windows
    CONFIG_FOLDER = Path(os.getenv('LOCALAPPDATA')) / 'Gitora'
else:  # Linux/macOS
    CONFIG_FOLDER = Path.home() / '.config' / 'Gitora'

CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_FOLDER / "config.json"
