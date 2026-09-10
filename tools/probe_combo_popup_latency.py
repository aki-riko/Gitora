# coding: utf-8
"""弹层打开延迟探针：同一场景下测引擎的 Fluent.ComboBox 冷开/热开主线程耗时。

用途
----
排查「下拉/菜单点击响应慢」时，先用它把**引擎弹层自身**的成本测出来，避免把
业务侧主线程占用误判成引擎问题；配合 ``GITORA_STALL_TRACE`` 的停顿观测一起看。

判据
----
- 热开（已预热）中位数应在数毫秒级；若热开就已经几十毫秒以上，问题在弹层路径。
- 冷开（未预热直接点）明显高于热开，说明命中 ``PopupPrewarm`` 的 hover 竞态：
  预热只由鼠标进入触发且经 0ms 定时器延后，快速 hover→点击会走冷路径。
- 换 ``--engine`` 指向不同引擎版本，可判断某个差异是**新旧版本共有**还是**新版本已修**。

用法
----
    # A：venv 里 pip 安装的那一版（打包态用的引擎）
    .venv/Scripts/python.exe tools/probe_combo_popup_latency.py

    # B：开发态加载的引擎源码仓库
    .venv/Scripts/python.exe tools/probe_combo_popup_latency.py --engine D:/PrismQML/PrismQML

需要真实可见窗口（D3D11），不能在 offscreen 下测量；运行约 10 秒。
结果以单行 JSON 输出，便于两版对比。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QSG_RHI_BACKEND", "d3d11")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

parser = argparse.ArgumentParser(description="测量 PrismQML ComboBox 弹层打开延迟")
parser.add_argument(
    "--engine",
    default="",
    help="引擎源码仓库路径；给出时优先于 site-packages（模拟开发态加载）",
)
parser.add_argument("--rounds", type=int, default=7, help="热开采样次数")
args = parser.parse_args()

if args.engine:
    sys.path.insert(0, args.engine)

import prismqml  # noqa: E402
from prismqml import qml_path  # noqa: E402

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlComponent, QQmlEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: F401,E402
from PySide6.QtTest import QTest  # noqa: E402


SCENE = """
import QtQuick
import QtQuick.Window
import PrismQML as Fluent

Window {
    id: probeWindow
    objectName: "probeWindow"
    width: 620
    height: 420
    visible: true
    color: Fluent.Enums.cardColor

    Fluent.ComboBox {
        id: combo
        objectName: "combo"
        x: 60
        y: 60
        width: 240
        height: 32
        model: ["alpha", "beta", "gamma"]
    }
}
"""


def pump(milliseconds: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QQmlEngine()
    engine.addImportPath(str(qml_path().parent))
    component = QQmlComponent(engine)
    component.setData(
        SCENE.encode("utf-8"), QUrl.fromLocalFile("ComboPopupLatencyProbe.qml")
    )
    deadline = time.monotonic() + 5
    while (
        component.status() == QQmlComponent.Status.Loading
        and time.monotonic() < deadline
    ):
        pump(20)
    if component.status() != QQmlComponent.Status.Ready:
        print(f"QML 加载失败: {component.errors()}", file=sys.stderr)
        return 1

    window = component.create()
    if window is None:
        print(f"窗口创建失败: {component.errors()}", file=sys.stderr)
        return 1
    window.show()
    window.requestActivate()
    pump(500)

    combo = window.findChild(object, "combo")
    if combo is None:
        print("找不到 ComboBox，场景未按预期加载", file=sys.stderr)
        return 1
    center = QPoint(60 + 120, 60 + 16)
    app.processEvents()

    # 冷开：不 hover 直接点击，命中未预热路径
    start = time.perf_counter()
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center, 10)
    cold_ms = (time.perf_counter() - start) * 1000
    pump(500)
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center, 10)
    pump(450)

    # 悬停完成预热后再测热开
    QTest.mouseMove(window, center)
    pump(400)
    warm_ms: list[float] = []
    for _ in range(max(1, args.rounds)):
        start = time.perf_counter()
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center, 10)
        warm_ms.append((time.perf_counter() - start) * 1000)
        pump(430)
        QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, center, 10)
        pump(400)

    print(json.dumps({
        "engine_version": prismqml.__version__,
        "engine_file": prismqml.__file__,
        "qml_import_dir": str(qml_path()),
        "cold_click_ms": round(cold_ms, 1),
        "warm_click_ms": [round(value, 1) for value in warm_ms],
        "warm_median_ms": round(statistics.median(warm_ms), 1),
        "top_level_windows": len(QGuiApplication.topLevelWindows()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
