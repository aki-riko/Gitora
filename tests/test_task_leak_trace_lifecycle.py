# coding: utf-8
"""任务泄漏观测必须走受管线程，并且能被停止。

两条独立契约：

1. **不得手写线程**：生产代码禁止 ``threading.Thread`` / ``QThread`` 子类，
   长驻观测也必须交给 PrismQML 统一管理（由
   ``tests/test_prism_task_migration.py`` 的 AST 门禁强制）。
2. **必须可停止**：采样循环是长驻任务，若没有停止信号，线程会带着对引擎
   内部对象的引用活到解释器关闭，既掩盖真实泄漏信号，也会在退出期触发
   ``QThread: Destroyed while thread is still running``。

第 2 条曾真实缺失：改为受管线程后循环仍不可中断，唯一可见症状是退出期
崩溃——普通单测看不出，必须显式验证 ``TaskHandle.finished``。

注意：断言走 AST / 代码行而非整份源码的字符串匹配，避免被注释里的说明
文字误伤（本文件注释就包含这些写法作为历史记录）。
"""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "app_qml" / "backend" / "task_leak_trace.py"


def _tree() -> ast.Module:
    return ast.parse(TARGET.read_text(encoding="utf-8"), filename=str(TARGET))


def _calls_named(tree: ast.Module, owner: str, attr: str) -> list[int]:
    """返回形如 ``owner.attr(...)`` 的调用行号。"""
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == owner
            and function.attr == attr
        ):
            lines.append(node.lineno)
    return lines


def test_reporter_uses_managed_thread_not_hand_written_one() -> None:
    """采样线程必须经引擎 run_in_thread 创建，不得手写 threading.Thread。"""
    tree = _tree()
    assert _calls_named(tree, "threading", "Thread") == [], (
        "长驻采样线程必须走 PrismQML 的 run_in_thread，不得手写 threading.Thread"
    )
    assert _calls_named(tree, "threading", "Event"), "停止信号应基于 threading.Event"
    # run_in_thread 必须被真正调用（而非仅导入）
    assert _calls_named(tree, "run_in_thread", "__call__") or any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_in_thread"
        for node in ast.walk(tree)
    ), "缺少 run_in_thread(...) 调用"


def test_reporter_loop_is_stoppable() -> None:
    """循环必须由 Event.wait 驱动并能被外部置位打断。"""
    tree = _tree()
    loops = [node for node in ast.walk(tree) if isinstance(node, ast.While)]
    assert loops, "未找到采样循环"
    for node in loops:
        body_has_true = (
            isinstance(node.test, ast.Constant) and node.test.value is True
        )
        assert not body_has_true, (
            f"第 {node.lineno} 行是不可中断的 while True，"
            "采样线程会活到解释器关闭"
        )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "wait"
        for node in ast.walk(tree)
    ), "停止信号必须使用 Event.wait 以支持立即唤醒"
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "stop_task_leak_trace"
        for node in ast.walk(tree)
    ), "缺少 stop_task_leak_trace 停止入口"


@pytest.mark.skipif(
    os.environ.get("GITORA_RUN_TASK_LEAK_LIFECYCLE") != "1",
    reason="需要真实 QThread 生命周期，默认关闭以免拖慢常规套件",
)
def test_reporter_thread_finishes_after_stop() -> None:
    """真实启动一次，断言 stop 后 TaskHandle.finished 触发。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["GITORA_TASK_LEAK_TRACE"] = "1"
    os.environ.setdefault("GITORA_TASK_LEAK_TRACE_INTERVAL_MS", "1000")

    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance() or QCoreApplication([])  # noqa: F841

    from app_qml.backend import task_leak_trace as trace

    try:
        assert trace.install_task_leak_trace() is True
        handle = trace._reporter_handle
        assert handle is not None

        state = {"finished": False}
        handle.finished.connect(lambda: state.__setitem__("finished", True))

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.02)

        trace.stop_task_leak_trace()

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not state["finished"]:
            app.processEvents()
            time.sleep(0.02)

        assert state["finished"] is True, "stop 之后受管线程仍未结束"
    finally:
        trace.stop_task_leak_trace()
