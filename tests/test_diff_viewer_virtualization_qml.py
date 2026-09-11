# coding: utf-8
"""验证 DiffViewer 虚拟化渲染:大 diff 只实例化可见窗口的行。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBE_MARKER = "[DIFF_VIRTUALIZATION_PROBE]"


def _build_large_diff(hunks: int = 100, lines_per_hunk: int = 25) -> str:
    """构造 2000+ 行的合成 unified diff,含一条 600 字符长行。"""
    out = ["diff --git a/big.txt b/big.txt", "index 1111111..2222222 100644",
           "--- a/big.txt", "+++ b/big.txt"]
    old_no = 1
    new_no = 1
    for h in range(hunks):
        out.append(f"@@ -{old_no},{lines_per_hunk} +{new_no},{lines_per_hunk} @@")
        for i in range(lines_per_hunk):
            if i % 3 == 0:
                out.append(f"-old {h} {i} " + "x" * 20)
                out.append(f"+new {h} {i} " + "y" * 20)
                old_no += 1
                new_no += 1
            elif i % 3 == 1:
                out.append(f" ctx {h} {i} " + "c" * 20)
                old_no += 1
                new_no += 1
            else:
                out.append(" ctx " + "L" * 600)  # 长行:触发横向滚动
                old_no += 1
                new_no += 1
    return "\n".join(out) + "\n"


LARGE_DIFF = _build_large_diff()

PROBE_SOURCE = b"""
import QtQuick
import "components"

DiffViewer {
    id: viewer
    width: 800
    height: 600
}
"""


def test_large_diff_renders_only_visible_window() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "tests.test_diff_viewer_virtualization_qml", "--probe"],
        cwd=str(ROOT),
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    for token in ("virtualized=true", "hscroll=true"):
        assert token in result.stdout, diagnostic


def _run_probe() -> int:
    from PySide6.QtCore import QEventLoop, QTimer, QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    from app_qml.backend.git_bridge import GitBridge

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    bridge = GitBridge()
    engine.rootContext().setContextProperty("GitBridge", bridge)
    engine.rootContext().setContextProperty("LargeDiff", LARGE_DIFF)

    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(ROOT / "app_qml" / "qml" / "DiffProbe.qml"))
    component.setData(PROBE_SOURCE, base_url)
    errors = [error.toString() for error in component.errors()]
    assert component.status() == QQmlComponent.Status.Ready, errors
    viewer = component.create(engine.rootContext())
    assert viewer is not None, errors

    viewer.setProperty("rawDiff", LARGE_DIFF)

    def pump_until(predicate, timeout_ms: int = 10000) -> bool:
        loop = QEventLoop()
        deadline = [timeout_ms]

        def tick() -> None:
            if predicate() or deadline[0] <= 0:
                loop.quit()
                return
            deadline[0] -= 25
            QTimer.singleShot(25, tick)

        QTimer.singleShot(25, tick)
        loop.exec()
        return bool(predicate())

    def _js_list(value):
        return value.toVariant() if hasattr(value, "toVariant") else value

    rows = viewer.property("_viewRows")
    assert rows is not None
    reached = pump_until(lambda: len(_js_list(viewer.property("_viewRows"))) > 1500)
    assert reached, f"rows not ready: {len(_js_list(viewer.property('_viewRows')))}"

    view_rows = _js_list(viewer.property("_viewRows"))
    pool = _js_list(viewer.property("_pool"))
    row_height = float(viewer.property("rowHeight"))
    total = len(view_rows)
    pool_size = len(pool)

    # 虚拟化核心断言:池大小远小于总行数(800x600 视口 + overscan)
    assert total > 1500, total
    assert pool_size < 120, f"pool={pool_size} total={total}"
    # 池内首行已绑定数据
    first = pool[0] if pool_size > 0 else None
    assert first is not None and first.property("row") is not None
    # 内容高度 = 行数 x 行高
    canvas_height = row_height * total

    # 横向滚动:长行使内容宽超过视口宽
    hscroll_ok = pump_until(lambda: float(viewer.property("_contentWidth")) > 800)
    assert hscroll_ok, f"contentWidth={viewer.property('_contentWidth')}"

    print(
        f"{PROBE_MARKER} virtualized=true pool={pool_size} total={total} "
        f"rowHeight={row_height:.1f} canvasHeight={canvas_height:.1f} hscroll=true"
    )

    viewer.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--probe"]:
        raise SystemExit("usage: python -m tests.test_diff_viewer_virtualization_qml --probe")
    raise SystemExit(_run_probe())
