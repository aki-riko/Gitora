# coding: utf-8
"""
Gitora 应用设置
"""
import os
from pathlib import Path

# change DEBUG to False if you want to compile the code to exe
DEBUG = "__compiled__" not in globals()


YEAR = 2025
AUTHOR = "aki-riko"
VERSION = "v1.5.2"
APP_NAME = "Gitora"
APP_USER_MODEL_ID = "PrismQML.Gitora"
# 项目地址
HELP_URL = "https://github.com/aki-riko/Gitora"
REPO_URL = "https://github.com/aki-riko/Gitora"
FEEDBACK_URL = "https://github.com/aki-riko/Gitora/issues"
DOC_URL = "https://github.com/aki-riko/Gitora#readme"

# 自动更新:GitHub 仓库 "owner/repo"(用于查 latest release)
UPDATE_REPO = "aki-riko/Gitora"
# 从 release assets 中挑安装包的关键词(安装包名形如 Gitora-Setup-x.y.z.exe)
UPDATE_ASSET_KEYWORD = "Setup"
_INNO_SETUP_SILENT_ARGS = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-"


def _resolve_installer_silent_args(platform_name: str | None = None) -> str:
    """仅为 Windows Inno Setup 返回静默安装参数。"""
    current_platform = platform_name or os.name
    return _INNO_SETUP_SILENT_ARGS if current_platform == "nt" else ""


# 安装包启动参数:Windows 下静默覆盖旧版,不显示向导、不自动重启应用。
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
