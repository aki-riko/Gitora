# coding: utf-8
"""AI 模型下拉框刷新链路的真实 QML 回归测试。

覆盖用户复现路径：点击「刷新模型」后，远端模型列表必须真正替换下拉框选项。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from PySide6.QtCore import QMetaObject, QObject

from app.common.ai_commit_credentials import SystemCredentialStore
from app.common.ai_commit_provider import ModelProvider
from app.common.ai_commit_settings import AiCommitSettingsStore
from app.common.git_service import GitService
from app_qml.backend.ai_commit_bridge import AiCommitBridge


ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = ROOT / "app_qml" / "qml" / "components"
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _js_list(value: object) -> list:
    """把 QML 侧 JS 数组读成 Python 列表。"""
    to_variant = getattr(value, "toVariant", None)
    if callable(to_variant):
        value = to_variant()
    return [str(item) for item in (value or [])]


class _MemoryCredentialBackend:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.values[(service, username)]


class _MutableModelProvider(ModelProvider):
    """可替换模型清单的假远端提供方，模拟远端把模型换掉。"""

    def __init__(self, models: tuple[str, ...]) -> None:
        self.models = models
        self.list_calls = 0

    @property
    def provider_id(self) -> str:
        return "openai_responses"

    def list_models(self) -> tuple[str, ...]:
        self.list_calls += 1
        return self.models

    def generate_plan(self, request, cancel_event=None):
        raise AssertionError("本测试不生成提交方案")


def _probe_source() -> bytes:
    component_url = COMPONENT_DIR.as_uri()
    return f"""
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import \"{component_url}\"

Window {{
    width: 1180
    height: 720
    visible: false

    AiCommitSettingsCard {{
        id: card
        objectName: \"aiCommitSettingsCard\"
        width: 1120
        height: 700
    }}
}}
""".encode("utf-8")


def _create_scene(tmp_path: Path, provider: _MutableModelProvider):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from prismqml import qml_path

    app = QGuiApplication.instance() or QGuiApplication([])

    store = AiCommitSettingsStore(DEFAULTS, tmp_path / "ai_commit.json")
    store.save(store.load().with_user_values({
        "enabled": True,
        "provider": "openai_responses",
        "local_endpoint": "http://127.0.0.1:11434",
        "local_model": "local-model",
        "remote_endpoint": "https://example.invalid/v1",
        "remote_model": "old-model",
    }))
    bridge = AiCommitBridge(
        GitService(),
        store,
        provider_factory=lambda _settings, _key: provider,
        credential_store=SystemCredentialStore(
            "Gitora.AiCommit.Test", _MemoryCredentialBackend()
        ),
    )

    engine = QQmlEngine()
    engine.addImportPath(str(qml_path().parent))
    engine.rootContext().setContextProperty("AiCommitBridge", bridge)

    component = QQmlComponent(engine)
    component.setData(
        _probe_source(),
        QUrl.fromLocalFile(str(ROOT / "tests" / "AiCommitSettingsProbe.qml")),
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
    return app, engine, component, window, bridge


def _destroy_scene(app, engine, component, window) -> None:
    window.destroy()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()


def _wait_for_refresh(results: list[tuple], expected: int) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and len(results) < expected:
        _pump(20)
    assert len(results) >= expected, "刷新模型未在超时前返回结果"
    # 信号之后仍需一拍，让 QML 处理完 busy 状态与下拉框更新。
    _pump(50)


def test_refresh_models_replaces_dropdown_options(tmp_path: Path) -> None:
    """远端模型被换掉后，刷新模型必须让下拉框出现新模型。"""
    provider = _MutableModelProvider(("alpha-model", "beta-model"))
    app, engine, component, window, bridge = _create_scene(tmp_path, provider)
    try:
        connection = window.findChild(QObject, "aiConnectionSection")
        combo = window.findChild(QObject, "remoteModelCombo")
        assert connection is not None and combo is not None
        assert connection.property("providerIndex") == 1

        results: list[tuple] = []
        bridge.modelListFinished.connect(lambda *args: results.append(args))

        # 真实路径：连接区发出 fetchModelsRequested，由卡片调用后端拉取模型。
        assert QMetaObject.invokeMethod(connection, "fetchModelsRequested")
        _wait_for_refresh(results, 1)
        provider_id, ok, models, message = results[0]
        assert provider_id == "openai_responses"
        assert ok, message
        assert models == ["alpha-model", "beta-model"]

        available = _js_list(connection.property("remoteModels"))
        assert available == ["alpha-model", "beta-model"], available
        # ComboBox 的 count() 是 QML 方法而不是属性，直接读它的 model 才等价于下拉列表内容。
        assert _js_list(combo.property("model")) == available, (
            f"下拉框选项 {_js_list(combo.property('model'))} 与可用模型 {available} 不一致"
        )
        assert combo.property("currentIndex") == 0
        assert combo.property("currentText") == "alpha-model"

        # 远端把模型换掉后再次刷新，下拉框必须换成新模型。
        provider.models = ("gamma-model",)
        assert QMetaObject.invokeMethod(connection, "fetchModelsRequested")
        _wait_for_refresh(results, 2)
        assert results[1][1] is True, results[1][3]

        available = _js_list(connection.property("remoteModels"))
        assert available == ["gamma-model"], available
        assert _js_list(combo.property("model")) == ["gamma-model"]
        assert combo.property("currentIndex") == 0
        assert combo.property("currentText") == "gamma-model"
    finally:
        _destroy_scene(app, engine, component, window)
