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
    # 带全 QML 运行时模块(QtQuick.Window 等核心模块,否则运行时报 module not installed)。
    "--include-qt-plugins=qml",
    # 排除 Qt 的构建中间产物/实验模块:它们含 objects-RelWithDebInfo/.qt 这类非 bundle
    # 格式文件,会让 mac ad-hoc codesign --deep 报 "bundle format unrecognized"。
    # 🔴 pattern 匹配的是【目标路径】(.app 内相对路径),不能以 */ 开头(文档明确);
    # assetdownloader 是 Qt labs 实验模块 Gitora 不用,整目录排除。
    "--noinclude-data-files=PySide6/qml/Qt/labs/assetdownloader/*",
    "--noinclude-data-files=PySide6/qml/**/objects-*/*",
    "--macos-create-app-bundle",
    # 注:不用 --macos-app-create-dmg。Nuitka 在 mac 强制 --deep ad-hoc 签名整个 .app,
    # 会撞 Qt labs/assetdownloader 的构建残留(.qt 非 bundle 格式)而签名失败 → 命令非零退出。
    # 改由 CI 后处理:容忍此步退出码 → rm 脏目录 → codesign 重签 → hdiutil 自己打 dmg。
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
    "--product-version=1.0.7",
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
app = os.path.join(OUT, "main_qml.app")
app_built = os.path.isdir(app)
if rc == 0:
    print(f"\n[build] 完成!产物: {app}")
elif app_built:
    # Nuitka mac 强制签名,撞 Qt 构建残留会非零退出,但 .app 通常已在签名前生成。
    # CI 后处理会清脏文件+重签;此处不当致命错,让 CI 接管。
    print(f"\n[build] Nuitka 退出码 {rc},但 .app 已生成({app}) — 交 CI 后处理重签/打 dmg")
    rc = 0
else:
    print(f"\n[build] 失败且无 .app,退出码 {rc}")
sys.exit(rc)
