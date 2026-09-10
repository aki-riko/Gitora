# coding: utf-8
"""设置页「提交用户」卡片的真实 QML 行为测试。

覆盖两点：
1. 全局 Git 配置能被真正读进输入框（用真实 git 配置的值做期望）；
2. 不同配置状态下，卡片必须给出正确提示——尤其是邮箱不是邮箱地址、
   以及"不想用私人邮箱"时的替代方案。
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from PySide6.QtCore import QObject, Signal, Slot


ROOT = Path(__file__).resolve().parents[1]
VIEW_DIR = ROOT / "app_qml" / "qml" / "views"


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _global_git_config(key: str) -> str:
    """读取本机真实的全局 git 配置值，作为输入框的期望。"""
    result = subprocess.run(
        ["git", "config", "--global", key],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


class _FakeTask(QObject):
    """模拟 PrismQML TaskHandle 的两个结果信号。"""

    succeeded = Signal("QVariant")
    failed = Signal("QVariant")


class _FakeGitBridge(QObject):
    """只实现设置页用到的全局用户查询。"""

    def __init__(self) -> None:
        super().__init__()
        self.task: _FakeTask | None = None

    @Slot(result=QObject)
    def getGlobalUserInfo(self) -> QObject:
        self.task = _FakeTask()
        return self.task


def _probe_source() -> bytes:
    view_url = VIEW_DIR.as_uri()
    return f"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import \"{view_url}\"

Window {{
    width: 1100
    height: 900
    visible: false

    SettingsView {{
        id: settingsView
        objectName: \"settingsView\"
        anchors.fill: parent
    }}
}}
""".encode("utf-8")


def _create_scene(git_bridge: QObject):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from prismqml import qml_path

    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(qml_path().parent))
    context = engine.rootContext()
    context.setContextProperty("GitBridge", git_bridge)
    context.setContextProperty("ConfigManager", None)
    context.setContextProperty("AppInfo", {})
    context.setContextProperty("AiCommitBridge", None)

    component = QQmlComponent(engine)
    component.setData(
        _probe_source(),
        QUrl.fromLocalFile(str(ROOT / "tests" / "SettingsViewProbe.qml")),
    )
    deadline = time.monotonic() + 5
    while (
        component.status() == QQmlComponent.Status.Loading
        and time.monotonic() < deadline
    ):
        _pump(20)
    assert component.status() == QQmlComponent.Status.Ready, component.errors()

    window = component.create()
    assert window is not None, component.errors()
    _pump(50)
    view = window.findChild(QObject, "settingsView")
    assert view is not None
    return app, engine, component, window, view


def _destroy_scene(app, engine, component, window) -> None:
    window.destroy()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()


def test_git_user_fields_load_real_global_config() -> None:
    """输入框必须显示真实的全局 Git 用户名/邮箱，而不是空白表单。"""
    expected_name = _global_git_config("user.name")
    expected_email = _global_git_config("user.email")
    if not expected_name and not expected_email:
        pytest.skip("本机没有全局 user.name / user.email，无法验证读取链路")

    from app_qml.backend.git_bridge import GitBridge

    bridge = GitBridge()
    bridge._poll_timer.stop()
    app, engine, component, window, view = _create_scene(bridge)
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not view.property("_gitUserLoaded"):
            _pump(20)
        assert view.property("_gitUserLoaded"), "全局 Git 配置未在超时前读取完成"
        assert not view.property("_gitUserReadFailed")
        assert view.property("_gitUserName") == expected_name
        assert view.property("_gitUserEmail") == expected_email

        # 输入框本身也必须显示出来，而不是只有内部状态正确。
        name_input = window.findChild(QObject, "gitUserNameInput")
        email_input = window.findChild(QObject, "gitUserEmailInput")
        assert name_input is not None and email_input is not None
        assert name_input.property("text") == expected_name
        assert email_input.property("text") == expected_email
    finally:
        _destroy_scene(app, engine, component, window)
        bridge.deleteLater()
        app.processEvents()


def test_git_user_hint_explains_email_and_anonymous_alternative() -> None:
    """邮箱不像邮箱地址时要给出可执行提示，而不是只让用户填私人邮箱。"""
    bridge = _FakeGitBridge()
    app, engine, component, window, view = _create_scene(bridge)
    try:
        assert bridge.task is not None

        # 全局配置缺失：说明两项都必须填的原因。
        bridge.task.succeeded.emit(["", ""])
        _pump(20)
        assert view.property("_gitUserLoaded")
        assert view.property("_gitUserNeedsAttention")
        missing_hint = str(view.property("_gitUserStateText"))
        assert "用户名和邮箱" in missing_hint
        assert "无法提交" in missing_hint

        # 真实场景：全局邮箱是 aki_riko 这种非邮箱地址。
        bridge.task.succeeded.emit(["aki-riko", "aki_riko"])
        _pump(20)
        malformed_hint = str(view.property("_gitUserStateText"))
        assert view.property("_gitUserNeedsAttention")
        assert "aki-riko <aki_riko>" in malformed_hint
        assert "@" in malformed_hint
        assert "users.noreply.github.com" in malformed_hint

        # 配好之后不再提示异常，并说明保存去向。
        bridge.task.succeeded.emit([
            "aki-riko", "aki-riko@users.noreply.github.com"
        ])
        _pump(20)
        assert not view.property("_gitUserNeedsAttention")
        ok_hint = str(view.property("_gitUserStateText"))
        assert "aki-riko <aki-riko@users.noreply.github.com>" in ok_hint
        assert "全局 Git 配置" in ok_hint

        # 读取失败要如实说明，不能装作"没配置"。
        bridge.task.failed.emit("boom")
        _pump(20)
        assert view.property("_gitUserReadFailed")
        assert "重新读取" in str(view.property("_gitUserStateText"))
    finally:
        _destroy_scene(app, engine, component, window)
