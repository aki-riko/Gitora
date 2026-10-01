# coding: utf-8
"""任务同步对象泄漏观测层（默认关闭，只观测、不改变任何既有行为）。

背景：Windows 上 CPython 的每个 ``threading.Lock/RLock/Event/Semaphore/Condition``
实例各占 1 个内核 Semaphore 句柄，因此"句柄只增不减"等价于"存活的 Python
并发原语对象只增不减"。PrismQML 每个后台任务创建的同步对象固定为：

    TaskHandle   -> _waited_outcome_lock(Lock) + _backend_lock(RLock)   = 2 个
    _TaskControl -> _lock(Lock) + _backend_stopped(Event)               = 2 个

实测打包版净泄漏约 3.1 个/秒、任务提交率约 1.55/秒，即**恰好 2 个/任务**。
本观测层用于判定这 2 个究竟属于 TaskHandle 还是 _TaskControl：

- ``activeHandles`` 持续增长  -> TaskHandle 未被回收（它会引用 control，
  因此两者应各涨 2 个，合计 4 个/任务，与实测的 2 个不符）。
- ``liveControls`` 持续增长而 ``activeHandles`` 稳定 -> _TaskControl 被
  TaskHandle.destroyed 上那个捕获 control 的 lambda 吊住（正是实测的 2 个/任务）。

同时记录 ``liveRunnables`` / ``liveEvents``，用于排除线程池持有 runnable 或
事件桥未 deleteLater 的旁支可能。

开关（默认关闭；关闭时不注册任何 patch、零开销）：
- ``GITORA_TASK_LEAK_TRACE=1``：启用观测。
- ``GITORA_TASK_LEAK_TRACE_INTERVAL_MS``：采样间隔（默认 10000，最小 1000）。
该缺陷已由 PrismQML 0.5.0.35 起在引擎侧修复（``task_runner`` 的 ``_connect_events``
与 ``QTimer.singleShot`` 回调改用只弱引用宿主的 ``WeakMethodRelay``）。本观测保留，
用于同类回归的快速判定：正常情况下 ``liveHandles`` 应跟随 ``activeHandles``，
而不是跟随 ``created``。

采样与写盘全部在后台守护线程完成，主线程只承担一次整数自增与一次
``WeakSet.add``，不触碰磁盘与枚举，符合主线程耗时预算。
"""

from __future__ import annotations

import os
import threading
import time
import weakref

from app.common.logger import get_logger

_ENV_ENABLE = "GITORA_TASK_LEAK_TRACE"
_ENV_INTERVAL = "GITORA_TASK_LEAK_TRACE_INTERVAL_MS"
_DEFAULT_INTERVAL_MS = 10000
_MIN_INTERVAL_MS = 1000

_lock = threading.Lock()
_stats = {
    "created": 0, "pool": 0, "thread": 0,
    # release_events_later 内部分支计数：用于判定打破 handle<->events 环的那一步
    # 究竟断在哪里（未被调用 / events 为 None / isValid 误报 / deleteLater 调了不生效）。
    "releaseCalls": 0, "eventsNone": 0, "eventsInvalid": 0, "deleteCalled": 0,
}
_live_controls: weakref.WeakSet | None = None
_live_runnables: weakref.WeakSet | None = None
_live_events: weakref.WeakSet | None = None
_live_handles: weakref.WeakSet | None = None
# 最近一次创建出来的 TaskHandle 的弱引用。WeakSet 的迭代顺序与插入顺序无关，
# 直接 next(iter(...)) 很可能取到补丁之前建立的旧对象，从而掩盖当前代码路径
# 的真实引用情况；诊断时必须稳定取样"最新那个"。
_last_handle_ref: weakref.ReferenceType | None = None
_live_executions: weakref.WeakSet | None = None
_runner_module = None
_installed = False
_reporter_started = False


def _env_flag(name: str) -> bool:
    """与 main_qml.py / crash_trace.py 同语义的布尔开关解析。"""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def task_leak_trace_enabled() -> bool:
    """观测是否开启（供启动日志判定；关闭时零开销）。"""
    return _env_flag(_ENV_ENABLE)


def _interval_ms() -> int:
    raw = os.environ.get(_ENV_INTERVAL, "").strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_INTERVAL_MS
    return max(_MIN_INTERVAL_MS, value)


def _track(target_set, obj) -> None:
    if target_set is not None and obj is not None:
        try:
            target_set.add(obj)
        except TypeError:
            pass


def _install_patches() -> bool:
    """包装引擎的任务创建入口，只增加计数与弱引用登记。"""
    global _live_controls, _live_runnables, _live_events, _runner_module, _installed
    global _live_handles, _live_executions

    try:
        import prismqml.python.core.task_runner as tr
        from prismqml.python.core import _task_backends, _task_execution
    except Exception as exc:                       # noqa: BLE001
        get_logger("Gitora").warning("[TASK_LEAK] 观测安装失败: %r", exc)
        return False

    _live_controls = weakref.WeakSet()
    _live_runnables = weakref.WeakSet()
    _live_events = weakref.WeakSet()
    _live_handles = weakref.WeakSet()
    _live_executions = weakref.WeakSet()
    _runner_module = tr

    original_create = tr._create_task

    def traced_create(*args, **kwargs):
        global _last_handle_ref
        handle, execution = original_create(*args, **kwargs)
        with _lock:
            _stats["created"] += 1
        _last_handle_ref = weakref.ref(handle)
        _track(_live_handles, handle)
        _track(_live_executions, execution)
        _track(_live_controls, getattr(handle, "_control", None))
        _track(_live_events, getattr(handle, "_events", None))
        return handle, execution

    tr._create_task = traced_create

    original_pool = tr.run_in_pool
    original_thread = tr.run_in_thread

    def traced_pool(*args, **kwargs):
        with _lock:
            _stats["pool"] += 1
        return original_pool(*args, **kwargs)

    def traced_thread(*args, **kwargs):
        with _lock:
            _stats["thread"] += 1
        return original_thread(*args, **kwargs)

    tr.run_in_pool = traced_pool
    tr.run_in_thread = traced_thread

    original_runnable_init = _task_backends._PoolRunnable.__init__

    def traced_runnable_init(self, *args, **kwargs):
        original_runnable_init(self, *args, **kwargs)
        _track(_live_runnables, self)

    _task_backends._PoolRunnable.__init__ = traced_runnable_init

    # 观测打破 handle<->events 环的那一步：只统计，仍调用原实现保持行为不变。
    original_release = _task_execution._TaskExecution.release_events_later

    def traced_release(self):
        events = getattr(self, "_events", None)
        with _lock:
            _stats["releaseCalls"] += 1
            if events is None:
                _stats["eventsNone"] += 1
        if events is not None:
            try:
                import shiboken6

                if shiboken6.isValid(events):
                    with _lock:
                        _stats["deleteCalled"] += 1
                else:
                    with _lock:
                        _stats["eventsInvalid"] += 1
            except Exception:                  # noqa: BLE001
                pass
        return original_release(self)

    _task_execution._TaskExecution.release_events_later = traced_release

    _installed = True
    return True


def _self_test_signal_gc() -> bool:
    """自测：在**当前进程**里，信号连接是否阻止宿主对象被回收。

    解释执行下 Python 的 method 实现了 tp_traverse，含 bound method 的引用环
    可被 gc 回收（实测 sink 被回收）。若打包产物里回收不掉，说明 Nuitka 生成的
    ``compiled_method`` 未参与 GC 追踪，其 ``__self__`` 引用对 gc 不可见 ——
    这正是 TaskHandle 被 _relay_* 槽吊住、每任务漏 4 个内核 Semaphore 的根因。

    返回 True 表示"回收不掉"（即打包产物存在该问题）。
    """
    try:
        import gc
        import weakref

        from PySide6.QtCore import QObject, Signal

        class _Src(QObject):
            sig = Signal()

        class _Sink(QObject):
            def __init__(self) -> None:
                super().__init__()
                self.source = _Src()
                self.source.sig.connect(self.on_sig)

            def on_sig(self) -> None:
                pass

        sink = _Sink()
        sink_ref = weakref.ref(sink)
        del sink
        gc.collect()
        return sink_ref() is not None
    except Exception:                                  # noqa: BLE001
        return False


def _start_reporter() -> None:
    """在后台守护线程内周期采样并写日志（不占用主线程）。"""
    global _reporter_started
    if _reporter_started:
        return
    _reporter_started = True

    logger = get_logger("Gitora")

    def loop() -> None:
        import ctypes
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessHandleCount.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
        ]
        kernel32.GetProcessHandleCount.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()

        interval = _interval_ms() / 1000.0
        previous = None
        previous_active = 0
        previous_controls = 0
        while True:
            time.sleep(interval)
            try:
                handle_count = wintypes.DWORD(0)
                kernel32.GetProcessHandleCount(process, ctypes.byref(handle_count))
                with _lock:
                    snapshot = dict(_stats)
                active = len(_runner_module._ACTIVE_HANDLES)
                controls = len(_live_controls) if _live_controls is not None else -1
                runnables = len(_live_runnables) if _live_runnables is not None else -1
                handles = len(_live_handles) if _live_handles is not None else -1
                executions = (
                    len(_live_executions) if _live_executions is not None else -1
                )
                events = len(_live_events) if _live_events is not None else -1
                # 存活的 events 里 C++ 对象是否仍有效。用于区分两种截然不同的成因：
                #   eventsCppValid ≈ liveEvents -> deleteLater 没有真正删除 C++ 对象；
                #   eventsCppValid ≈ 0          -> C++ 已删除，是 Python 包装被环吊住。
                events_cpp_valid = 0
                if _live_events is not None:
                    import shiboken6

                    for candidate in list(_live_events):
                        try:
                            if shiboken6.isValid(candidate):
                                events_cpp_valid += 1
                        except Exception:          # noqa: BLE001
                            pass
                logger.info(
                    "[TASK_LEAK] created=%d pool=%d thread=%d activeHandles=%d "
                    "liveHandles=%d liveExecutions=%d liveControls=%d "
                    "liveRunnables=%d liveEvents=%d eventsCppValid=%d "
                    "processHandles=%d",
                    snapshot["created"], snapshot["pool"], snapshot["thread"],
                    active, handles, executions, controls,
                    runnables, events, events_cpp_valid, handle_count.value,
                )
                logger.info(
                    "[TASK_LEAK] 释放链 releaseCalls=%d eventsNone=%d "
                    "eventsInvalid=%d deleteCalled=%d",
                    snapshot["releaseCalls"], snapshot["eventsNone"],
                    snapshot["eventsInvalid"], snapshot["deleteCalled"],
                )
                # 引用者分析：直接列出谁在持有泄漏对象。断开信号连接后仍未回收，
                # 说明存在信号连接之外的强引用，这里把它照出来（诊断期开销可接受）。
                try:
                    import gc
                    from collections import Counter as _Counter

                    def _referrer_kinds(obj):
                        if obj is None:
                            return None
                        kinds = _Counter()
                        active_dict = (
                            _runner_module._ACTIVE_HANDLES
                            if _runner_module is not None else None
                        )
                        for ref in gc.get_referrers(obj):
                            if isinstance(ref, dict):
                                if ref is active_dict:
                                    kinds["dict:_ACTIVE_HANDLES"] += 1
                                elif len(ref) < 64:
                                    keys = [type(k).__name__ for k in list(ref)[:4]]
                                    kinds[f"dict(len={len(ref)},keys={keys})"] += 1
                                else:
                                    kinds[f"dict(len={len(ref)})"] += 1
                                continue
                            if isinstance(ref, (list, tuple, set)):
                                kinds[f"{type(ref).__name__}(len={len(ref)})"] += 1
                                continue
                            name = type(ref).__name__
                            if name in ("method", "compiled_method",
                                        "builtin_function_or_method"):
                                func = getattr(ref, "__func__", None)
                                label = (
                                    getattr(func, "__name__", None)
                                    or getattr(ref, "__name__", "?")
                                )
                                kinds[f"{name}:{label}"] += 1
                            else:
                                kinds[name] += 1
                        return dict(kinds)

                    handle_sample = (
                        _last_handle_ref() if _last_handle_ref is not None
                        else None
                    )
                    if handle_sample is None and _live_handles is not None:
                        handle_sample = next(iter(_live_handles), None)
                    logger.info(
                        "[TASK_LEAK] handle 的引用者类型分布 = %s",
                        _referrer_kinds(handle_sample),
                    )
                except Exception as exc:           # noqa: BLE001
                    logger.warning("[TASK_LEAK] 引用者分析失败: %r", exc)
                if previous is not None:
                    delta = handle_count.value - previous
                    logger.info(
                        "[TASK_LEAK] 本周期句柄增量=%+d (%.2f/秒)，"
                        "activeHandles 增量=%+d，liveControls 增量=%+d",
                        delta, delta / interval,
                        active - previous_active, controls - previous_controls,
                    )
                previous = handle_count.value
                previous_active = active
                previous_controls = controls
            except Exception as exc:               # noqa: BLE001
                logger.warning("[TASK_LEAK] 采样失败: %r", exc)

    threading.Thread(target=loop, daemon=True, name="TaskLeakTrace").start()


def install_task_leak_trace() -> bool:
    """安装任务泄漏观测（env 门控，默认关闭时零开销）。"""
    installed = False
    if task_leak_trace_enabled():
        if _installed or _install_patches():
            get_logger("Gitora").info(
                "[TASK_LEAK] 已启用任务同步对象泄漏观测，间隔 %dms", _interval_ms()
            )
            get_logger("Gitora").info(
                "[TASK_LEAK] 自测：信号连接后宿主能否被 gc 回收 —— 回收不掉=%s"
                "（解释执行下应为 False）",
                _self_test_signal_gc(),
            )
            _start_reporter()
            installed = True
    return installed
