# coding: utf-8
"""
Gitess QML 版入口(阶段 0 脚手架)

依赖方式:sys.path 引用本地 FluentQML 源码(D:/FluentQML)。
用 FluentQML 的 App 类启动,自动完成 DPI/消息处理器/register_types/addImportPath。
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

from app_qml.backend.git_bridge import GitBridge  # noqa: E402


def main() -> int:
    app = App(sys.argv)
    engine = app.engine

    # 注册后端到 QML
    git_bridge = GitBridge()
    config_manager = getConfigManager()
    ctx = engine.rootContext()
    ctx.setContextProperty("GitBridge", git_bridge)
    ctx.setContextProperty("ConfigManager", config_manager)

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
