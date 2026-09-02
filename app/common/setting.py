# coding: utf-8
"""
Gitora 应用设置
"""
import os
from pathlib import Path

# change DEBUG to False if you want to compile the code to exe
DEBUG = "__compiled__" not in globals()


YEAR = 2026
AUTHOR = "aki-riko"
VERSION = "v1.7.0"
APP_NAME = "Gitora"
APP_USER_MODEL_ID = "PrismQML.Gitora"
APP_WINDOW_WIDTH = 1100
APP_WINDOW_HEIGHT = 720
APP_SPLASH_SUBTITLE = "正在加载..."
# 项目地址
HELP_URL = "https://github.com/aki-riko/Gitora"
PRISMQML_URL = "https://github.com/aki-riko/PrismQML"
REPO_URL = "https://github.com/aki-riko/Gitora"
FEEDBACK_URL = "https://github.com/aki-riko/Gitora/issues"
DOC_URL = "https://github.com/aki-riko/Gitora#readme"

# 自动更新:GitHub 仓库 "owner/repo"(用于查 latest release)
UPDATE_REPO = "aki-riko/Gitora"
# 从 release assets 中挑安装包的关键词(安装包名形如 Gitora-Setup-x.y.z.exe)
UPDATE_ASSET_KEYWORD = "Setup"
_INNO_SETUP_SILENT_ARGS = "/SILENT /SUPPRESSMSGBOXES /NORESTART /SP-"


def _resolve_installer_silent_args(platform_name: str | None = None) -> str:
    """仅为 Windows Inno Setup 返回静默安装参数。"""
    current_platform = platform_name or os.name
    return _INNO_SETUP_SILENT_ARGS if current_platform == "nt" else ""


# 安装包启动参数:Windows 下隐藏向导但显示安装进度，完成后启动一次新版。
# 机器级安装仍由 Windows 显示不可绕过的 UAC 安全提示。
INSTALLER_SILENT_ARGS = _resolve_installer_silent_args()

# 使用系统用户数据目录
def _resolve_config_folder(platform_name: str | None = None) -> Path:
    current_platform = platform_name or os.name
    if current_platform == 'nt':  # Windows
        return Path(os.getenv('LOCALAPPDATA')) / 'Gitora'
    xdg_config_home = os.getenv('XDG_CONFIG_HOME')
    config_root = (
        Path(xdg_config_home) if xdg_config_home else Path.home() / '.config'
    )
    return config_root / 'Gitora'


CONFIG_FOLDER = _resolve_config_folder()

CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_FOLDER / "config.json"
# PrismQML 引擎配置使用 Gitora 自己的用户目录，避免与 Gallery 共用 ~/.prismqml/app.json。
PRISMQML_CONFIG_FILE = CONFIG_FOLDER / "prismqml.json"
