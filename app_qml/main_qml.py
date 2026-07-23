# coding: utf-8
"""
Gitora QML 版入口(基于 PrismQML 的 Git GUI)

依赖方式:sys.path 引用本地 PrismQML 源码(默认 D:/PrismQML,可用环境变量 PRISMQML_ROOT 覆盖)。
用 PrismQML 的 App 类启动,自动完成 DPI/消息处理器/register_types/addImportPath。
QML 版基于 PrismQML(MIT),无 QFluentWidgets Pro / License 依赖。
"""
import os
import sys
import time


SETTINGS_NAV_POLL_MS = 50
SETTINGS_NAV_TIMEOUT_MS = 5000

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


def _start_settings_navigation_selftest(engine, finish) -> None:
    """切到真实设置页并等待懒加载栈确认页面就绪。"""
    from PySide6.QtCore import QTimer

    root = engine.rootObjects()[0]
    window = root.property("windowInstance")
    target_index = root.property("settingsPageIndex")
    state = {"finished": False}
    deadline = time.monotonic() + SETTINGS_NAV_TIMEOUT_MS / 1000

    def complete(ok: bool, message: str) -> None:
        if state["finished"]:
            return
        state["finished"] = True
        finish(ok, message)

    def on_warnings(warnings) -> None:
        for warning in warnings:
            message = warning.toString()
            if "SettingsView.qml" in message or "AiCommitSettingsCard.qml" in message:
                complete(False, message[-1000:])
                return

    def poll() -> None:
        stack = window.property("stackedWidget")
        is_ready = (
            stack is not None
            and stack._isPageLoaded(target_index)
            and stack.property("currentIndex") == target_index
            and stack.property("_displayIndex") == target_index
        )
        if is_ready:
            complete(True, "SettingsView 已加载")
        elif time.monotonic() >= deadline:
            complete(False, "SettingsView 在超时前未加载并显示")
        else:
            QTimer.singleShot(SETTINGS_NAV_POLL_MS, poll)

    if window is None or not isinstance(target_index, int) or target_index < 0:
        complete(False, "主窗口或设置页索引不可用")
        return
    engine.warnings.connect(on_warnings)
    if not window.setProperty("currentIndex", target_index):
        complete(False, "无法切换到设置页索引")
        return
    QTimer.singleShot(0, poll)


def _cleanup_credential_selftest(store, account: str) -> None:
    try:
        store.delete(account)
    except Exception as exc:  # noqa: BLE001
        print(f"[SELFTEST] 系统凭据清理失败: {type(exc).__name__}")


def _create_credential_selftest_context():
    import uuid

    from app.common.ai_commit_credentials import SystemCredentialStore
    from app.common.ai_commit_settings import AiCommitSettingsStore

    service = (
        f"{AiCommitSettingsStore().load().credential_service}"
        f".Selftest.{uuid.uuid4().hex}"
    )
    return (
        SystemCredentialStore(service),
        "packaged-selftest",
        f"gitora-selftest-{uuid.uuid4().hex}",
    )


def _credential_selftest_failure(exc: Exception) -> tuple[bool, str]:
    from app.common.ai_commit_credentials import CredentialStoreError

    message = (
        str(exc)
        if isinstance(exc, CredentialStoreError)
        else f"系统凭据验证异常: {type(exc).__name__}"
    )
    print(f"[SELFTEST] 系统凭据库验证失败: {message}")
    return False, message


def _credential_selftest_step(step: str) -> None:
    print(f"[SELFTEST] 系统凭据库验证阶段: {step}")


def _run_system_credential_selftest() -> tuple[bool, str]:
    """在唯一临时条目上验证当前用户的原生凭据库写、读、删。"""
    store = None
    account = ""
    stored = False
    try:
        _credential_selftest_step("初始化原生后端")
        store, account, secret = _create_credential_selftest_context()
        _credential_selftest_step("写入临时凭据")
        store.set(account, secret)
        stored = True
        _credential_selftest_step("读取临时凭据")
        if store.get(account) != secret:
            return False, "系统凭据读取值不一致"
        _credential_selftest_step("删除临时凭据")
        if not store.delete(account):
            return False, "系统凭据删除未生效"
        _credential_selftest_step("确认临时凭据已删除")
        if store.get(account):
            return False, "系统凭据删除后仍可读取"
        stored = False
    except Exception as exc:  # noqa: BLE001
        return _credential_selftest_failure(exc)
    finally:
        if stored and store is not None:
            _cleanup_credential_selftest(store, account)
    return True, "原生系统凭据写入、读取和删除均通过"


class _SelftestCoordinator:
    def __init__(self, app, timer, pending: int):
        self._app = app
        self._timer = timer
        self._pending = pending
        self._finished = False

    def finish(self, label: str, ok: bool, message: str) -> None:
        if self._finished:
            return
        result = "成功" if ok else "失败"
        print(f"[SELFTEST] {label}{result}: {message}")
        if not ok:
            self._finished = True
            self._timer.singleShot(0, lambda: self._app.exit(2))
            return
        self._pending -= 1
        if self._pending == 0:
            self._finished = True
            self._timer.singleShot(0, lambda: self._app.exit(0))


def _start_requested_selftests(
    timer, engine, ai_commit_bridge, coordinator, requested
) -> None:
    needs_ai, needs_settings, needs_credentials = requested
    if needs_settings:
        timer.singleShot(
            0,
            lambda: _start_settings_navigation_selftest(
                engine,
                lambda ok, message: coordinator.finish(
                    "设置页导航", ok, message
                ),
            ),
        )
    if needs_ai:
        ai_commit_bridge.connectionTestFinished.connect(
            lambda ok, message: coordinator.finish("AI 连接检测", ok, message)
        )
        timer.singleShot(0, ai_commit_bridge.testConnection)
        timer.singleShot(
            15000,
            lambda: coordinator.finish("AI 连接检测", False, "连接检测超时"),
        )
    if needs_credentials:
        timer.singleShot(
            0,
            lambda: coordinator.finish(
                "系统凭据库验证", *_run_system_credential_selftest()
            ),
        )


def _schedule_selftest(app, engine, ai_commit_bridge) -> None:
    """验证 QML 启动；可选验证设置导航与打包态 AI 连接。"""
    from PySide6.QtCore import QTimer

    print("[SELFTEST] QML 加载成功,rootObjects =", len(engine.rootObjects()))
    requested = (
        bool(os.environ.get("GITESS_AI_CONNECTION_SELFTEST")),
        bool(os.environ.get("GITESS_SETTINGS_NAV_SELFTEST")),
        bool(os.environ.get("GITESS_CREDENTIAL_SELFTEST")),
    )
    if not any(requested):
        QTimer.singleShot(1500, app.quit)
        return
    coordinator = _SelftestCoordinator(app, QTimer, sum(map(int, requested)))
    _start_requested_selftests(
        QTimer, engine, ai_commit_bridge, coordinator, requested
    )

# PRISMQML_PKG_DIR = .../prismqml 包目录(其下含 PrismQML/qmldir 与 python/)
PRISMQML_PKG_DIR = _resolve_prismqml_dir()
if not PRISMQML_PKG_DIR:
    print("[ERROR] 找不到 PrismQML:请先 pip install prismqml,或设 PRISMQML_ROOT 指向源码仓库")
    sys.exit(1)

os.environ.setdefault("QT_LOGGING_RULES", "qt.text.font.db=false")
os.environ.setdefault("QML_XHR_ALLOW_FILE_READ", "1")

from PySide6.QtCore import QUrl  # noqa: E402

from app.common.setting import APP_USER_MODEL_ID  # noqa: E402

os.environ.setdefault("PRISMQML_APP_USER_MODEL_ID", APP_USER_MODEL_ID)

from prismqml import App  # noqa: E402
from prismqml.python.config import getConfigManager  # noqa: E402
from prismqml.python.providers import get_clipboard_helper  # noqa: E402

from app_qml.backend.git_bridge import GitBridge  # noqa: E402
from app_qml.backend.ai_commit_bridge import AiCommitBridge  # noqa: E402
from app_qml.backend.ai_commit_plan_bridge import AiCommitPlanBridge  # noqa: E402
from app_qml.backend.qml_render_bridge import QmlRenderBridge  # noqa: E402
from app_qml.backend.window_icon_bridge import WindowIconBridge  # noqa: E402


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
    ai_commit_bridge = AiCommitBridge(git_bridge.service)
    ai_commit_plan_bridge = AiCommitPlanBridge(
        git_bridge.service, ai_commit_bridge
    )
    config_manager = getConfigManager()
    from app_qml.backend.repo_scanner import RepoScanner
    repo_scanner = RepoScanner()
    qml_render_bridge = QmlRenderBridge()
    window_icon_bridge = WindowIconBridge()
    ctx = engine.rootContext()
    ctx.setContextProperty("GitBridge", git_bridge)
    ctx.setContextProperty("AiCommitBridge", ai_commit_bridge)
    ctx.setContextProperty("AiCommitPlanBridge", ai_commit_plan_bridge)
    ctx.setContextProperty("ConfigManager", config_manager)
    ctx.setContextProperty("ClipboardHelper", get_clipboard_helper())
    ctx.setContextProperty("RepoScanner", repo_scanner)
    ctx.setContextProperty("QmlRenderBridge", qml_render_bridge)
    ctx.setContextProperty("WindowIconBridge", window_icon_bridge)
    app._qml_render_bridge = qml_render_bridge
    app._window_icon_bridge = window_icon_bridge  # keep native icon handles alive
    app._ai_commit_bridge = ai_commit_bridge
    app._ai_commit_plan_bridge = ai_commit_plan_bridge
    git_bridge.repoPathChanged.connect(ai_commit_bridge.invalidateRepo)
    git_bridge.statusChanged.connect(ai_commit_bridge.invalidateWorkspace)
    git_bridge.repoPathChanged.connect(ai_commit_plan_bridge.invalidateRepo)
    git_bridge.statusChanged.connect(ai_commit_plan_bridge.invalidateWorkspace)
    ai_commit_bridge.settingsChanged.connect(ai_commit_plan_bridge.invalidateSettings)
    # 启动后台扫描(延迟启动,不阻塞窗口显示)
    from PySide6.QtCore import QTimer as _QTimer
    _QTimer.singleShot(1500, repo_scanner.start)
    # 退出时停止扫描线程,避免 QThread 销毁时仍在运行
    app.aboutToQuit.connect(repo_scanner.shutdown)

    # 应用信息(版本/作者/链接)从 setting.py 读取,避免 QML 内硬编码
    from app.common.setting import (
        VERSION, AUTHOR, YEAR, HELP_URL, FEEDBACK_URL, APP_USER_MODEL_ID,
        UPDATE_REPO, UPDATE_ASSET_KEYWORD, INSTALLER_SILENT_ARGS,
    )
    ctx.setContextProperty("AppInfo", {
        "version": VERSION,
        "author": AUTHOR,
        "year": str(YEAR),
        "helpUrl": HELP_URL,
        "feedbackUrl": FEEDBACK_URL,
        "appUserModelId": APP_USER_MODEL_ID,
        "installerSilentArgs": INSTALLER_SILENT_ARGS,
    })

    # 由 PrismQML 注入引擎级更新后端,供 QML AutoUpdater 门面消费。
    # App 持有实例生命周期;自检进程会在启动检查定时器触发前退出,不会联网。
    app.enable_auto_update(UPDATE_REPO, VERSION, UPDATE_ASSET_KEYWORD)

    # addImportPath 指向 prismqml 包目录(其下 PrismQML/qmldir 提供 QML 模块)
    engine.addImportPath(PRISMQML_PKG_DIR)

    # PrismQML 图标目录 URL(供 QML 拼接导航图标路径)
    icons_dir = os.path.join(PRISMQML_PKG_DIR, "PrismQML", "controls", "icons", "fluent")
    ctx.setContextProperty("FluentIconsDir", QUrl.fromLocalFile(icons_dir + os.sep).toString())

    # 应用 logo(窗口/任务栏图标),复用原版 app/resource/images/logo.png
    logo_path = os.path.join(GITESS_ROOT, "app", "resource", "images", "logo.png")
    icon_path = os.path.join(GITESS_ROOT, "app", "resource", "images", "logo.ico")
    ctx.setContextProperty("AppLogo", QUrl.fromLocalFile(logo_path).toString() if os.path.isfile(logo_path) else "")
    ctx.setContextProperty("AppIconFile", QUrl.fromLocalFile(icon_path).toString() if os.path.isfile(icon_path) else "")

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

    # 启动检查由主窗口的 PrismQML AutoUpdater 在加载完成后发起。
    # SELFTEST 1.5s 即退出,早于其 3s 定时器。

    # headless 自检:默认验证 QML；构建验收可额外验证打包态 AI 本地连接。
    if os.environ.get("GITESS_QML_SELFTEST"):
        _schedule_selftest(app, engine, ai_commit_bridge)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
