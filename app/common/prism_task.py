# coding: utf-8
"""PrismQML 后台任务的轻量信号连接工具。

本模块不实现线程、Worker 或调度器；任务创建、线程池、结果回主线程和退出清理
全部交给 PrismQML。这里只统一连接回调并把 ``TaskFailure`` 解包为真实异常。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prismqml import TaskFailure, TaskHandle, run_in_pool


def task_exception(failure: object) -> BaseException:
    """从引擎失败载荷中取出原始异常。"""
    if isinstance(failure, TaskFailure):
        return failure.exception
    if isinstance(failure, BaseException):
        return failure
    return RuntimeError(str(failure))


def submit_to_pool(
    function: Callable[..., Any],
    /,
    *args: Any,
    on_success: Callable[[Any], None] | None = None,
    on_failure: Callable[[BaseException], None] | None = None,
    on_progress: Callable[[Any], None] | None = None,
    on_cancelled: Callable[[], None] | None = None,
    on_finished: Callable[[], None] | None = None,
    **kwargs: Any,
) -> TaskHandle:
    """提交到 PrismQML 全局线程池，并在 Qt 主线程执行所给回调。"""
    handle = run_in_pool(function, *args, **kwargs)
    if on_success is not None:
        handle.succeeded.connect(on_success)
    if on_failure is not None:
        handle.failed.connect(
            lambda failure: on_failure(task_exception(failure))
        )
    if on_progress is not None:
        handle.progress.connect(on_progress)
    if on_cancelled is not None:
        handle.cancelled.connect(on_cancelled)
    if on_finished is not None:
        handle.finished.connect(on_finished)
    return handle


__all__ = ["submit_to_pool", "task_exception"]
