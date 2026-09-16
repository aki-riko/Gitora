# coding: utf-8
"""启动卡死取证探针(Gitora 启动无响应时使用)。

为什么需要它:Gitora 的“启动卡死”表现为启动页停在“开始圆环揭幕”之后,
主线程再没有回到事件循环(Windows 记录 AppHangB1)。这种现场在 Python 层没有
traceback,常规日志止于崩溃前最后一行,Qt 侧也不产生错误。本探针用
faulthandler 的看门狗线程周期性 dump **所有线程的 Python 栈**,因此即使主线程
被同步调用卡住,也能拿到它当时停在哪个调用链上。

用法(项目根目录,直接粘贴,不要套 ssh):

    .venv\\Scripts\\python.exe tools\\startup_hang_probe.py

默认行为:
1. 打开主线程停顿观测 ``GITORA_STALL_TRACE=1``(无间隔心跳,只有停顿才落记录);
2. 每 ``GITORA_HANG_PROBE_INTERVAL`` 秒(默认 5)把所有线程栈追加写入
   ``%LOCALAPPDATA%\\Gitora\\logs\\hang_probe_YYYYMMDD_HHMMSS.txt``;
3. 正常启动 ``app_qml/main_qml.py``(真实窗口,不走自检、不改单实例行为)。

卡死后:直接关掉卡死的窗口(或结束进程),把 ``hang_probe_*.txt`` 的最后一段
交给排查者。若需要无人值守,可设 ``GITORA_HANG_PROBE_SECONDS=30`` 让探针在
指定秒数后硬退出,避免留下卡死窗口。
"""
from __future__ import annotations

import faulthandler
import os
import runpy
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN_QML = ROOT / "app_qml" / "main_qml.py"
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Gitora" / "logs"
INTERVAL_S = float(os.environ.get("GITORA_HANG_PROBE_INTERVAL", "5"))
HARD_EXIT_S = float(os.environ.get("GITORA_HANG_PROBE_SECONDS", "0"))


def _open_stack_file():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"hang_probe_{stamp}.txt"
    handle = open(path, "a", buffering=1, encoding="utf-8")
    return path, handle


def main() -> int:
    if not MAIN_QML.is_file():
        print(f"[PROBE] 找不到入口: {MAIN_QML}")
        return 2

    # 主线程停顿观测:停顿记录形如 [STALL_TRACE] #N gap=...ms busy=... windows=...
    os.environ.setdefault("GITORA_STALL_TRACE", "1")

    path, handle = _open_stack_file()
    handle.write(
        f"===== 探针启动 {datetime.now():%Y-%m-%d %H:%M:%S} pid={os.getpid()} "
        f"interval={INTERVAL_S:g}s hard_exit={HARD_EXIT_S:g}s =====\n"
    )
    faulthandler.enable(file=handle)
    faulthandler.dump_traceback_later(INTERVAL_S, repeat=True, file=handle)
    print(f"[PROBE] 线程栈写入: {path}")
    print("[PROBE] 主线程停顿观测: GITORA_STALL_TRACE=1")
    print("[PROBE] 启动 app_qml/main_qml.py(真实窗口)")

    if HARD_EXIT_S > 0:
        def _hard_exit() -> None:
            time.sleep(HARD_EXIT_S)
            handle.write(f"===== {HARD_EXIT_S:g}s 到点,硬退出 =====\n")
            handle.flush()
            os._exit(0)

        threading.Thread(target=_hard_exit, daemon=True).start()

    sys.argv = [str(MAIN_QML)]
    runpy.run_path(str(MAIN_QML), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
