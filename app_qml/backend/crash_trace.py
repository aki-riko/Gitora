# coding: utf-8
"""崩溃取证观测层（默认关闭，只观测、不改变任何既有行为）。

Gitora 的历史崩溃表现为 Qt 侧原生访问违例（0xC0000005），进程被直接终止：
Python 层拿不到 traceback，业务日志止于崩溃前最后一条。本模块补齐三样东西：

1. faulthandler —— Windows 上捕获 EXCEPTION_ACCESS_VIOLATION / 栈溢出，
   把崩溃时刻所有线程的 **Python 栈**写入独立文件，让原生崩溃也留下 Python 现场。
2. Qt 消息处理器 —— 把 Qt/QML 的 debug/info/warning/critical/fatal（含 `file:line`）
   转进 Gitora 日志，同时保持 Qt 默认的 stderr 输出不变。
3. QML 引擎告警钩子 —— `engine.warnings` 逐条落日志。

开关（默认全部关闭；关闭时不注册任何处理器、不改任何环境变量）：
- ``GITORA_CRASH_TRACE=1``：启用上面 1/2/3。
- ``GITORA_QML_TRACE=1``：额外打开 Qt/QML 详细日志
  （QML_IMPORT_TRACE、QSG_INFO、qt.qml.binding.removal.info）。
- ``GITORA_LOG_DIR=<dir>``：覆盖观测文件目录（默认跟随 Gitora 日志目录）。

注意：观测状态不是修复条件。排查结束后清理环境变量并完整重启应用。
"""

import faulthandler
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from app.common.logger import get_logger


# 保持文件对象与槽函数引用，避免被 GC 回收导致崩溃时写不出内容
_FAULT_STREAM = None
_WARNING_SLOTS = []


def _env_flag(name: str) -> bool:
    """与 main_qml.py 同语义的布尔开关解析。"""
    return os.environ.get(name, "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def crash_trace_enabled() -> bool:
    """崩溃取证观测是否开启（供 QML 面包屑判定，关闭时零开销）。"""
    return _env_flag("GITORA_CRASH_TRACE")


def _log_dir(logger) -> Path:
    """观测文件目录：优先环境变量覆盖，其次复用 logging 已配置的日志目录。"""
    override = os.environ.get("GITORA_LOG_DIR", "").strip()
    if override:
        return Path(override)
    for handler in logging.getLogger().handlers:
        base_name = getattr(handler, "baseFilename", None)
        if base_name:
            return Path(base_name).parent
    fallback = Path(tempfile.gettempdir()) / "Gitora" / "logs"
    logger.warning(
        "[CRASH_TRACE] 未能从日志器取得日志目录，观测文件回退到 %s", fallback
    )
    return fallback


def _enable_faulthandler(logger) -> str:
    """把崩溃时刻的 Python 栈写入独立文件，返回该文件路径。"""
    global _FAULT_STREAM

    directory = _log_dir(logger)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"gitora_crash_{datetime.now().strftime('%Y%m%d')}.log"
    _FAULT_STREAM = open(path, "a", encoding="utf-8", buffering=1)
    faulthandler.enable(file=_FAULT_STREAM, all_threads=True)
    logger.info("[CRASH_TRACE] faulthandler 已启用 -> %s", path)
    return str(path)


def _qt_level(mode: int) -> int:
    """QtMsgType -> logging 级别。"""
    from PySide6.QtCore import QtMsgType

    return {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }.get(mode, logging.INFO)


def _install_qt_message_handler(logger) -> None:
    """接管 Qt 消息：写 Gitora 日志，并保持 Qt 默认的 stderr 输出。"""
    from PySide6.QtCore import qInstallMessageHandler

    def _handler(mode, context, message) -> None:
        text = f"[QT] {message}"
        if context is not None and context.file:
            text = f"[QT] {context.file}:{context.line} {message}"
        logger.log(_qt_level(mode), text)
        stream = sys.stderr
        if stream is not None:
            stream.write(text + "\n")

    previous = qInstallMessageHandler(_handler)
    logger.info(
        "[CRASH_TRACE] Qt 消息处理器已安装（前一个处理器: %r）",
        previous is not None,
    )


def configure_trace_env() -> None:
    """在 QGuiApplication 构造前应用观测环境变量；默认关闭时不动任何变量。"""
    if not _env_flag("GITORA_QML_TRACE"):
        return
    os.environ.setdefault("QML_IMPORT_TRACE", "1")
    os.environ.setdefault("QSG_INFO", "1")
    extra_rule = "qt.qml.binding.removal.info=true"
    current = os.environ.get("QT_LOGGING_RULES", "")
    if extra_rule not in current:
        os.environ["QT_LOGGING_RULES"] = (
            f"{current};{extra_rule}" if current else extra_rule
        )


def attach_qml_warning_logger(engine) -> bool:
    """把 QML 引擎告警逐条写入日志，返回是否真正挂载。"""
    if not crash_trace_enabled():
        return False
    logger = get_logger("Gitora")

    def _on_warnings(warnings) -> None:
        for warning in warnings:
            logger.warning("[QML] %s", warning.toString())

    _WARNING_SLOTS.append(_on_warnings)
    engine.warnings.connect(_on_warnings)
    logger.info("[CRASH_TRACE] QML engine.warnings 已接入日志")
    return True


def install_crash_trace() -> bool:
    """安装崩溃取证观测（faulthandler + Qt 消息处理器），返回是否启用。"""
    if not crash_trace_enabled():
        return False

    logger = get_logger("Gitora")
    _enable_faulthandler(logger)
    _install_qt_message_handler(logger)
    logger.info(
        "[CRASH_TRACE] 已启用 crash_trace=1 qml_trace=%s",
        "1" if _env_flag("GITORA_QML_TRACE") else "0",
    )
    return True
