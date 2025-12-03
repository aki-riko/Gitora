# coding:utf-8
"""
Gitess - Git可视化工具
对新人友好的Git操作界面，支持一键暂存+提交+推送
"""
import os
import sys

from PySide6.QtCore import Qt, QTranslator
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentTranslator

# 设置Pro License
from qfluentwidgetspro import setLicense
setLicense("mGR3+Zzt2pWCCCUVLKMgV2zNviEC95enQKeF7HsypdeblJFuvJQXqvRxR/TLL7tnfSrCA1LZk1RGW5WdxHtB0OG/eqFBL5bEDB0rSaoORF5W0Spih7E/RffvgF98zDDk9q+Vqg6HP0lUTLamnTf9L/L/9PSFKQhijBUNQLHXRJdfQl7N10dKOng2tGfeSHXi50cAto85lPQK6B0Ce0F7WFvZwv4EI/IwgBsAunn+phLvVvuy2hLz3zP6EtRfKCMlVJDMIjIdd09ixyai1Dm4yBzaw3Aaa6f92vWZ3L5dkxXvUt0gxCIkJW+p+WZkt/KP")
# License已绑定机器码，硬编码到这里
PRO_LICENSE = ""  # 在这里粘贴你的License Key

if PRO_LICENSE:
    setLicense(PRO_LICENSE)

from app.common.config import cfg
from app.view.main_window import MainWindow


# enable dpi scale
if cfg.get(cfg.dpiScale) != "Auto":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))

# create application
app = QApplication(sys.argv)
app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

# internationalization
locale = cfg.get(cfg.language).value
translator = FluentTranslator(locale)
galleryTranslator = QTranslator()
galleryTranslator.load(locale, "app", ".", ":/app/i18n")

app.installTranslator(translator)
app.installTranslator(galleryTranslator)

# create main window
w = MainWindow()
w.show()

app.exec()
