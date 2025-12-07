# coding:utf-8
"""
Gitess - Git可视化工具
对新人友好的Git操作界面，支持一键暂存+提交+推送

Author: Apyrenia
"""
import os
import sys
import warnings

# 过滤QFluentWidgets库的弃用警告（来自库内部，无法修复）
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*globalPos.*")

from PySide6.QtCore import Qt, QTranslator, QLockFile, QDir
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox
from qfluentwidgets import FluentTranslator
from qfluentwidgetspro import setLicense, ProTranslator

# 设置Pro License
# License已绑定机器码，硬编码到这里
PRO_LICENSE = "mGR3+Zzt2pWCCCUVLKMgV2zNviEC95enQKeF7HsypdeblJFuvJQXqvRxR/TLL7tnfSrCA1LZk1RGW5WdxHtB0OG/eqFBL5bEDB0rSaoORF5W0Spih7E/RffvgF98zDDk9q+Vqg6HP0lUTLamnTf9L/L/9PSFKQhijBUNQLHXRJdfQl7N10dKOng2tGfeSHXi50cAto85lPQK6B0Ce0F7WFvZwv4EI/IwgBsAunn+phLvVvuy2hLz3zP6EtRfKCMlVJDMIjIdd09ixyai1Dm4yBzaw3Aaa6f92vWZ3L5dkxXvUt0gxCIkJW+p+WZkt/KP"  # 在这里粘贴你的License Key

if PRO_LICENSE:
    setLicense(PRO_LICENSE)

from app.common.config import cfg
from app.common.logger import Logger, get_logger
from app.view.main_window import MainWindow

# 初始化日志系统（必须在所有其他导入之前）
Logger.setup()
logger = get_logger("Main")


# enable dpi scale
if cfg.get(cfg.dpiScale) != "Auto":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

# create application
logger.info("创建QApplication")
app = QApplication(sys.argv)
app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# 单实例检查
logger.info("检查单实例")
lock_file_path = QDir.temp().absoluteFilePath("gitess.lock")
lock_file = QLockFile(lock_file_path)
lock_file.setStaleLockTime(0)  # 禁用过期锁检测

if not lock_file.tryLock(100):  # 尝试获取锁，超时100ms
    logger.warning("检测到Gitess已在运行")
    QMessageBox.warning(
        None,
        "Gitess已在运行",
        "Gitess已经在运行中，请勿重复启动。\n\n如果确认没有其他实例在运行，请删除临时文件：\n" + lock_file_path,
        QMessageBox.StandardButton.Ok
    )
    sys.exit(0)

# internationalization
locale = cfg.get(cfg.language).value
translator = FluentTranslator(locale)
proTranslator = ProTranslator()  # Pro组件翻译器
galleryTranslator = QTranslator()
galleryTranslator.load(locale, "app", ".", ":/app/i18n")

app.installTranslator(translator)
app.installTranslator(proTranslator)  # 安装Pro翻译器
app.installTranslator(galleryTranslator)

# 检测Git是否安装
from app.common.git_installer import gitInstaller
from PySide6.QtWidgets import QWidget

logger.info("检测Git安装状态")
installed, version = gitInstaller.check_git_installed()
logger.info(f"Git安装状态: {installed}, 版本: {version}")
if not installed:
    logger.warning("Git未安装，显示安装引导")
    temp_widget = QWidget()
    temp_widget.resize(800, 600)
    temp_widget.show()
    QApplication.processEvents()
    
    # 仅显示手动安装引导（避免主线程阻塞）
    gitInstaller.show_install_guide(temp_widget)
    
    temp_widget.close()
    sys.exit(0)

# create main window
logger.info("创建主窗口")
w = MainWindow()
w.show()
logger.info("主窗口已显示")

try:
    logger.info("进入事件循环")
    app.exec()
except Exception as e:
    logger.exception(f"应用程序异常退出: {e}")
    raise
finally:
    logger.info("应用程序退出")
