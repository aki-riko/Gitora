# coding: utf-8
"""
Gitora Nuitka 打包脚本(Windows, standalone/onedir)。

用法:  .venv\\Scripts\\python.exe build_nuitka.py
产物:  build_dist/main_qml.dist/  (含 main_qml.exe + 全部依赖)

要点:
- standalone(非 onefile):QML 应用 onefile 解压慢且易出问题,onedir 最稳。
- pyside6 插件:Nuitka 自动处理 Qt QML 运行时/插件。
- prismqml(932 QML + python + icons):include-package + include-package-data 带全部非py资源。
- app_qml/qml(主界面) 和 app/resource(logo/ico) 用 include-data-dir 解到 exe 同级。
  对应 main_qml.py 的 frozen 路径解析(GITESS_ROOT = exe 同级)。
"""
import os
import sys
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ENTRY = os.path.join(ROOT, "app_qml", "main_qml.py")
ICON = os.path.join(ROOT, "app", "resource", "images", "logo.ico")
OUT = os.path.join(ROOT, "build_dist")

# PySide6 的 QML 模块目录(Effects/Layouts/Controls 等)。Nuitka 的 pyside6 插件
# 不扫描"数据文件"里的 QML import,导致这些模块漏打 → 运行时 "module not installed"。
# 显式把整个 PySide6/qml 打进产物的 PySide6/qml(Qt 运行时在此查找 QML 模块)。
import PySide6 as _ps
_PYSIDE_DIR = os.path.dirname(_ps.__file__)
_PYSIDE_QML = os.path.join(_PYSIDE_DIR, "qml")

args = [
    PY, "-m", "nuitka",
    "--standalone",
    "--assume-yes-for-downloads",
    "--enable-plugin=pyside6",
    "--windows-console-mode=disable",
    "--output-filename=Gitora.exe",
    f"--windows-icon-from-ico={ICON}",
    # prismqml 整包 + 数据(QML/SVG/字体等非 .py 文件)
    "--include-package=prismqml",
    "--include-package-data=prismqml",
    # 后端包
    "--include-package=app",
    "--include-package=app_qml",
    # 界面 QML + 资源,解到 exe 同级(对应 frozen 路径)
    f"--include-data-dir={os.path.join(ROOT, 'app_qml', 'qml')}=app_qml/qml",
    f"--include-data-dir={os.path.join(ROOT, 'app', 'resource')}=app/resource",
    # PySide6 QML 模块(Effects/Layouts/Controls/Shapes/Dialogs 等),补 pyside6 插件漏打
    f"--include-data-dir={_PYSIDE_QML}=PySide6/qml",
    # include-data-dir 会跳过 .dll(当代码处理),但 QML 模块的 C++ 插件就是 .dll
    # (qquicklayoutsplugin.dll 等),必须用 include-data-files 显式按 *.dll 模式带上
    f"--include-data-files={_PYSIDE_QML}/=PySide6/qml/=**/*.dll",
    # QtQuick 子模块的核心实现库(Qt6QuickLayouts/Controls2/Shapes/Effects/Templates2 等),
    # pyside6 插件只打了 Qt6Quick.dll,这些子模块库漏打 → 插件 dll 依赖找不到。
    # 带到产物根(与 qt6quick.dll 同级,Qt 在此解析依赖)。
    f"--include-data-files={_PYSIDE_DIR}/Qt6Quick*.dll=./",
    # 产品元信息
    "--company-name=aki-riko",
    "--product-name=Gitora",
    "--product-version=1.0.7",
    "--file-description=Gitora - Git GUI",
    f"--output-dir={OUT}",
    ENTRY,
]

print("[build] Nuitka 打包开始(耗时数分钟)...")
print("[build] " + " ".join(args))
rc = subprocess.call(args, cwd=ROOT)
if rc == 0:
    exe = os.path.join(OUT, "main_qml.dist", "Gitora.exe")
    print(f"\n[build] 完成!产物: {exe}")
    print("[build] 真机运行该 exe 验证,然后用 ISCC 编译 installer.iss 出安装包。")
else:
    print(f"\n[build] 失败,退出码 {rc}")
sys.exit(rc)
