# coding: utf-8
"""
Gitess QML 版入口

依赖方式:sys.path 引用本地 FluentQML 源码(默认 D:/FluentQML,可用环境变量 FLUENTQML_ROOT 覆盖)。
用 FluentQML 的 App 类启动,自动完成 DPI/消息处理器/register_types/addImportPath。
QML 版基于 FluentQML(MIT),无 QFluentWidgets Pro / License 依赖。
"""
import os
import sys

# ---- 路径注入 ----
# 1) Gitess 项目根(让 app.common.* 可导入)
GITESS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GITESS_ROOT)

# 2) FluentQML 本地源码根(可被环境变量覆盖,避免硬编码)
FLUENTQML_ROOT = os.environ.get("FLUENTQML_ROOT", r"D:/FluentQML")
if not os.path.isdir(os.path.join(FLUENTQML_ROOT, "fluentqml")):
    print(f"[ERROR] 找不到 FluentQML 源码: {FLUENTQML_ROOT}")
    print("        设置环境变量 FLUENTQML_ROOT 指向 FluentQML 仓库根目录")
    sys.exit(1)
sys.path.insert(0, FLUENTQML_ROOT)

os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false")
os.environ.setdefault("QML_XHR_ALLOW_FILE_READ", "1")

from PySide6.QtCore import QUrl  # noqa: E402

from fluentqml import App  # noqa: E402
from fluentqml.python.config import getConfigManager  # noqa: E402
from fluentqml.python.providers import get_clipboard_helper  # noqa: E402

from app_qml.backend.git_bridge import GitBridge  # noqa: E402


def main() -> int:
    app = App(sys.argv)
    engine = app.engine

    # 单实例检查(共享内存);自检模式跳过
    if not os.environ.get("GITESS_QML_SELFTEST"):
        from PySide6.QtCore import QSharedMemory
        shared = QSharedMemory("Gitess_QML_SingleInstance_Key")
        if not shared.create(1):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Gitess 已在运行", "Gitess 已经在运行中,请勿重复启动。")
            return 0

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

    # 应用信息(版本/作者/链接)从 setting.py 读取,避免 QML 内硬编码
    from app.common.setting import VERSION, AUTHOR, YEAR, HELP_URL, FEEDBACK_URL
    ctx.setContextProperty("AppInfo", {
        "version": VERSION,
        "author": AUTHOR,
        "year": str(YEAR),
        "helpUrl": HELP_URL,
        "feedbackUrl": FEEDBACK_URL,
    })

    # 让 main.qml 能用字面量 import 解析 FluentQML 子目录
    fqml = os.path.join(FLUENTQML_ROOT, "fluentqml")
    engine.addImportPath(fqml)

    # FluentQML 图标目录 URL(供 QML 拼接导航图标路径,Gitess 在 FluentQML 仓库外故不能用相对路径)
    icons_dir = os.path.join(fqml, "FluentQML", "controls", "icons", "fluent")
    ctx.setContextProperty("FluentIconsDir", QUrl.fromLocalFile(icons_dir + os.sep).toString())

    # 加载主 QML
    qml_main = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml", "main.qml")
    engine.load(QUrl.fromLocalFile(qml_main))

    if not engine.rootObjects():
        print("[ERROR] 加载 main.qml 失败,检查组件路径或语法")
        return -1

    # headless 自检:设了 GITESS_QML_SELFTEST 则加载成功后定时退出
    if os.environ.get("GITESS_QML_SELFTEST"):
        from PySide6.QtCore import QTimer
        print("[SELFTEST] QML 加载成功,rootObjects =", len(engine.rootObjects()))
        QTimer.singleShot(1500, lambda: app.quit() if hasattr(app, "quit") else None)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
