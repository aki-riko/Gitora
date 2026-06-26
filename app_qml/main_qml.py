# coding: utf-8
"""
Gitora QML 版入口(基于 PrismQML 的 Git GUI)

依赖方式:sys.path 引用本地 PrismQML 源码(默认 D:/PrismQML,可用环境变量 PRISMQML_ROOT 覆盖)。
用 PrismQML 的 App 类启动,自动完成 DPI/消息处理器/register_types/addImportPath。
QML 版基于 PrismQML(MIT),无 QFluentWidgets Pro / License 依赖。
"""
import os
import sys

# ---- 是否为 Nuitka 打包态 ----
def _is_frozen() -> bool:
    return "__compiled__" in globals() or getattr(sys, "frozen", False)

# ---- 路径注入 ----
# 打包态:资源随 Nuitka standalone 解包(Windows/Linux 在主程序同级;
#   mac .app 里主程序在 Contents/MacOS/,数据可能在同级或 ../Resources)。
#   故 frozen 时按候选目录探测含 app_qml/qml 的那个,而非赌单一结构。
# 开发态:基于源码文件位置定位。
def _resolve_gitess_root() -> str:
    if not _is_frozen():
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    # 候选:主程序同级(Win/Linux 惯例) → mac bundle 的 ../Resources → 再上一级
    candidates = [
        exe_dir,
        os.path.join(exe_dir, "..", "Resources"),
        os.path.dirname(exe_dir),
    ]
    for c in candidates:
        if os.path.isdir(os.path.join(c, "app_qml", "qml")):
            return os.path.abspath(c)
    # 都没命中:回退主程序同级(让后续报错暴露真实结构,而非静默错路径)
    return exe_dir

GITESS_ROOT = _resolve_gitess_root()
sys.path.insert(0, GITESS_ROOT)

# 2) PrismQML 来源:优先用已安装的 pip 包(prismqml,import 名 prismqml);
#    若未安装,回退到本地源码探测(开发用)。
def _resolve_prismqml_dir():
    # 优先:已 pip 安装的 prismqml(import prismqml) — 打包态也走这里(已 include 进包)
    try:
        import prismqml as _f
        return os.path.dirname(_f.__file__)
    except ImportError:
        pass
    # 回退:本地源码(含 prismqml/__init__.py 的仓库根)
    candidates = []
    env = os.environ.get("PRISMQML_ROOT")
    if env:
        candidates.append(env)
    parent = os.path.dirname(GITESS_ROOT)
    candidates += [os.path.join(parent, "prismqml"), parent,
                   r"D:/PrismQML/prismqml", r"D:/PrismQML"]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "prismqml", "__init__.py")):
            sys.path.insert(0, c)
            import prismqml as _f
            return os.path.dirname(_f.__file__)
    return None

# PRISMQML_PKG_DIR = .../prismqml 包目录(其下含 PrismQML/qmldir 与 python/)
PRISMQML_PKG_DIR = _resolve_prismqml_dir()
if not PRISMQML_PKG_DIR:
    print("[ERROR] 找不到 PrismQML:请先 pip install prismqml,或设 PRISMQML_ROOT 指向源码仓库")
    sys.exit(1)

os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false")
os.environ.setdefault("QML_XHR_ALLOW_FILE_READ", "1")

from PySide6.QtCore import QUrl  # noqa: E402

from prismqml import App  # noqa: E402
from prismqml.python.config import getConfigManager  # noqa: E402
from prismqml.python.providers import get_clipboard_helper  # noqa: E402

from app_qml.backend.git_bridge import GitBridge  # noqa: E402


def main() -> int:
    app = App(sys.argv)
    engine = app.engine

    # 单实例检查(PrismQML SingleInstance:Windows Named Mutex + 本地套接字 IPC);
    # 自检模式跳过。第二实例会通知主实例激活窗口后静默退出,不弹框。
    app._single_instance = None
    if not os.environ.get("GITESS_QML_SELFTEST"):
        from prismqml import SingleInstance
        instance = SingleInstance("io.github.aki-riko.gitora")
        if not instance.try_lock():
            # 已有实例在运行:try_lock 内部已通知主实例激活窗口,这里直接退出
            return 0
        app._single_instance = instance  # 防止被 GC,保持锁 + IPC 监听

    # Git 安装检测
    from app.common.git_installer import gitInstaller
    installed, version = gitInstaller.check_git_installed()
    if not installed:
        from PySide6.QtWidgets import QMessageBox
        url = gitInstaller.get_download_url()
        QMessageBox.warning(
            None, "未检测到 Git",
            f"未检测到 Git 命令行工具,请先安装 Git。\n\n下载地址:\n{url}",
        )
        return 0

    # 注册后端到 QML
    git_bridge = GitBridge()
    config_manager = getConfigManager()
    from app_qml.backend.repo_scanner import RepoScanner
    repo_scanner = RepoScanner()
    ctx = engine.rootContext()
    ctx.setContextProperty("GitBridge", git_bridge)
    ctx.setContextProperty("ConfigManager", config_manager)
    ctx.setContextProperty("ClipboardHelper", get_clipboard_helper())
    ctx.setContextProperty("RepoScanner", repo_scanner)
    # 启动后台扫描(延迟启动,不阻塞窗口显示)
    from PySide6.QtCore import QTimer as _QTimer
    _QTimer.singleShot(1500, repo_scanner.start)
    # 退出时停止扫描线程,避免 QThread 销毁时仍在运行
    app.aboutToQuit.connect(repo_scanner.shutdown)

    # 应用信息(版本/作者/链接)从 setting.py 读取,避免 QML 内硬编码
    from app.common.setting import (
        VERSION, AUTHOR, YEAR, HELP_URL, FEEDBACK_URL,
        UPDATE_REPO, UPDATE_ASSET_KEYWORD, INSTALLER_SILENT_ARGS,
    )
    ctx.setContextProperty("AppInfo", {
        "version": VERSION,
        "author": AUTHOR,
        "year": str(YEAR),
        "helpUrl": HELP_URL,
        "feedbackUrl": FEEDBACK_URL,
        "installerSilentArgs": INSTALLER_SILENT_ARGS,
    })

    # 自动更新组件(PrismQML 引擎级 Updater,基于 GitHub Releases)。
    # 自检模式不联网。检测/下载/安装结果经信号回传给 QML(见 SettingsView)。
    from prismqml import Updater
    updater = Updater(UPDATE_REPO, VERSION, asset_keyword=UPDATE_ASSET_KEYWORD)
    ctx.setContextProperty("Updater", updater)
    app._updater = updater  # 防 GC,保持网络管理器存活

    # addImportPath 指向 prismqml 包目录(其下 PrismQML/qmldir 提供 QML 模块)
    engine.addImportPath(PRISMQML_PKG_DIR)

    # PrismQML 图标目录 URL(供 QML 拼接导航图标路径)
    icons_dir = os.path.join(PRISMQML_PKG_DIR, "PrismQML", "controls", "icons", "fluent")
    ctx.setContextProperty("FluentIconsDir", QUrl.fromLocalFile(icons_dir + os.sep).toString())

    # 应用 logo(窗口/任务栏图标),复用原版 app/resource/images/logo.png
    logo_path = os.path.join(GITESS_ROOT, "app", "resource", "images", "logo.png")
    ctx.setContextProperty("AppLogo", QUrl.fromLocalFile(logo_path).toString() if os.path.isfile(logo_path) else "")

    # 加载主 QML(打包态在 exe 同级 app_qml/qml,开发态在源码目录)
    if _is_frozen():
        qml_main = os.path.join(GITESS_ROOT, "app_qml", "qml", "main.qml")
    else:
        qml_main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml", "main.qml")
    engine.load(QUrl.fromLocalFile(qml_main))

    if not engine.rootObjects():
        print("[ERROR] 加载 main.qml 失败,检查组件路径或语法")
        return -1

    # 单实例激活:第二实例启动时,主实例把窗口提到前台(调 main.qml 的 activateWindow)
    if app._single_instance is not None:
        root_obj = engine.rootObjects()[0]

        def _on_activate():
            try:
                from PySide6.QtCore import QMetaObject
                QMetaObject.invokeMethod(root_obj, "activateWindow")
            except Exception as e:  # noqa: BLE001
                from app.common.logger import get_logger
                get_logger(__name__).warning(f"激活窗口失败: {e}")

        app._single_instance.activateRequested.connect(_on_activate)

    # 启动后的静默更新检查改由常驻的 RepoView(首页)在加载完成后发起,
    # 确保接收 Updater 信号的 Connections 已就绪(放 Python 端 QTimer 会早于 QML 接收方,
    # 导致 updateAvailable 信号无人接收而静默检查失效)。SELFTEST 1.5s 即退出,早于其 3s 定时器。

    # headless 自检:设了 GITESS_QML_SELFTEST 则加载成功后定时退出
    if os.environ.get("GITESS_QML_SELFTEST"):
        from PySide6.QtCore import QTimer
        print("[SELFTEST] QML 加载成功,rootObjects =", len(engine.rootObjects()))
        QTimer.singleShot(1500, lambda: app.quit() if hasattr(app, "quit") else None)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
