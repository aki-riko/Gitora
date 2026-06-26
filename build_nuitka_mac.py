# coding: utf-8
"""
Gitora Nuitka 打包脚本(macOS, .app bundle)。

⚠️ 必须在 macOS 上运行(Nuitka 不能从 Windows/Linux 交叉编译 mac 应用)。
   本地无 mac 时由 GitHub Actions 的 macos runner 执行(见 .github/workflows)。

用法:  python build_nuitka_mac.py
产物:  build_dist/main_qml.app  (双击即可运行的 .app bundle)

与 Windows 版(build_nuitka.py)的差异:
- --macos-create-app-bundle 产 .app(非 .exe)
- --macos-app-icon 接 PNG(Nuitka 自动转 .icns)
- QML C++ 插件是 .dylib(非 .dll)
- 无 console-mode(.app 本就不带终端)
"""
import os
import sys
import subprocess

if sys.platform != "darwin":
    print("[build] 本脚本仅在 macOS 运行(Nuitka 不能交叉编译 mac 应用)")
    sys.exit(1)

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
ENTRY = os.path.join(ROOT, "app_qml", "main_qml.py")
ICON = os.path.join(ROOT, "app", "resource", "images", "logo.png")  # Nuitka 自动转 .icns
OUT = os.path.join(ROOT, "build_dist")

# PySide6 的 QML 模块目录:pyside6 插件不扫"数据文件"里的 QML import,
# 显式整目录带上(与 Windows 版同策略,只是插件后缀是 .dylib)。
import PySide6 as _ps
_PYSIDE_DIR = os.path.dirname(_ps.__file__)
_PYSIDE_QML = os.path.join(_PYSIDE_DIR, "qml")

args = [
    PY, "-m", "nuitka",
    "--standalone",
    "--assume-yes-for-downloads",
    "--enable-plugin=pyside6",
    # 注:不手动加 --include-qt-plugins=qml。pyside6 的 Nuitka 插件已自动处理 QML 模块
    # (日志可见 "Included ... Qt QML datafile" + "Including Qt plugins ...qml...");
    # 手动再加会把 Qt 的构建中间产物(objects-RelWithDebInfo/.qt 等)塞进 Contents/MacOS,
    # 导致 mac ad-hoc codesign 报 "bundle format unrecognized" 而打包失败。
    "--macos-create-app-bundle",
    "--macos-app-create-dmg",          # 直接产 .dmg(Nuitka 内置,免额外打包步骤)
    "--macos-app-console-mode=disable", # 不带终端窗口
    f"--macos-app-icon={ICON}",
    "--macos-app-name=Gitora",
    # 产物内主程序名(.app/Contents/MacOS/ 下)
    "--output-filename=Gitora",
    # prismqml 整包 + 数据(QML/SVG/字体等非 .py 文件)
    "--include-package=prismqml",
    "--include-package-data=prismqml",
    # 后端包
    "--include-package=app",
    "--include-package=app_qml",
    # 界面 QML + 资源,解到 bundle 资源目录(对应 frozen 路径解析)
    f"--include-data-dir={os.path.join(ROOT, 'app_qml', 'qml')}=app_qml/qml",
    f"--include-data-dir={os.path.join(ROOT, 'app', 'resource')}=app/resource",
    # 产品元信息(流入 .app bundle 的 Info.plist)
    "--product-name=Gitora",
    "--product-version=1.0.4",
    "--file-description=Gitora - Git GUI",
    "--copyright=aki-riko",
    f"--output-dir={OUT}",
    ENTRY,
]

# PySide6 QML 模块:仅当 PySide6/qml 目录存在时才显式带上(Windows 有此目录;
# mac 的 PySide6 QML 布局不同/无此目录,Nuitka 的 pyside6 插件会自动处理)。
# 硬加不存在的目录会 FATAL(must specify existing source data directory)。
if os.path.isdir(_PYSIDE_QML):
    args.insert(-1, f"--include-data-dir={_PYSIDE_QML}=PySide6/qml")
    print(f"[build] PySide6/qml 存在,显式带上: {_PYSIDE_QML}")
else:
    print("[build] PySide6/qml 目录不存在(mac 布局),交由 pyside6 插件自动处理 QML 模块")

print("[build] Nuitka macOS 打包开始(耗时数分钟)...")
print("[build] " + " ".join(args))
rc = subprocess.call(args, cwd=ROOT)
if rc == 0:
    app = os.path.join(OUT, "main_qml.app")
    print(f"\n[build] 完成!产物: {app} + 同目录 .dmg")
    print("[build] 验证: open 该 .app;CI 里用 SELFTEST 跑 Contents/MacOS/Gitora。")
else:
    print(f"\n[build] 失败,退出码 {rc}")
sys.exit(rc)
