# coding: utf-8
"""仓库搜索弹层的过滤、路径映射与真实 QML 渲染测试。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDER_MARKER = "[REPOSITORY_SEARCH_MENU_RENDER]"
BEHAVIOR_MARKER = "[REPOSITORY_SEARCH_MENU_BEHAVIOR]"
PROBE_SOURCE = """
import QtQuick
import QtQuick.Layouts
import QtQuick.Window
import PrismQML as Fluent
import "components"

Window {
    id: root
    width: 820
    height: 620
    visible: true
    color: Fluent.Enums.backgroundColor

    RowLayout {
        id: trigger
        objectName: "repositoryMenuTrigger"
        x: Fluent.Enums.spacing.xl
        y: Fluent.Enums.spacing.xl
        spacing: -Fluent.Enums.border.thin

        Fluent.Button {
            text: "打开"
            icon: Fluent.Enums.icon.folder
        }

        Fluent.Button {
            icon: Fluent.Enums.icon.chevron_down
            Layout.preferredWidth: Fluent.Enums.controlSize.splitButtonArrowWidth
            Layout.minimumWidth: Fluent.Enums.controlSize.splitButtonArrowWidth
        }
    }

    RepositorySearchMenu {
        id: menu
        objectName: "repositorySearchMenu"
        useInWindowPopup: UseInWindowPopup
        useQtPopupWindow: !UseInWindowPopup
        pathFormatter: function(path) { return path }
    }

    Component.onCompleted: Qt.callLater(function() {
        menu.openFor(trigger, [
            "D:/MinecraftProject/mojin",
            "D:/API/kiro_rs",
            "D:/PrismQML/Gitora",
            "B:/Minecraft/Addons和modApi/已完成作品(新)/LuckyWorld"
        ])
    })
}
""".encode("utf-8")


def _probe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _run_probe(mode: str, output: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "tests.test_repository_search_menu_qml",
        mode,
    ]
    if output is not None:
        command.append(str(output))
    return subprocess.run(
        command,
        cwd=str(ROOT),
        env=_probe_environment(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )


def test_repository_search_menu_filters_and_keeps_original_path() -> None:
    result = _run_probe("--behavior-probe")
    diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    assert BEHAVIOR_MARKER in result.stdout, diagnostic
    assert result.stderr == "", diagnostic


def test_repository_search_menu_renders_search_above_results() -> None:
    with tempfile.TemporaryDirectory(prefix="gitora-repository-menu-qml-") as temp_dir:
        output = Path(temp_dir) / "repository-search-menu.png"
        result = _run_probe("--render-probe", output)
        diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert result.returncode == 0, diagnostic
        assert RENDER_MARKER in result.stdout, diagnostic
        assert output.is_file() and output.stat().st_size > 3_000, diagnostic


def _pump(milliseconds: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _create_scene(engine, use_in_window_popup: bool):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    engine.rootContext().setContextProperty(
        "UseInWindowPopup", use_in_window_popup
    )
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(
        str(ROOT / "app_qml" / "qml" / "RepositorySearchMenuProbe.qml")
    )
    component.setData(PROBE_SOURCE, base_url)
    for _ in range(50):
        if component.status() != QQmlComponent.Status.Loading:
            break
        _pump(20)
    errors = [error.toString() for error in component.errors()]
    if component.status() != QQmlComponent.Status.Ready:
        raise AssertionError(errors)
    root = component.create(engine.rootContext())
    if root is None:
        raise AssertionError(errors)
    return component, root


def _scene_objects(root):
    from PySide6.QtCore import QObject

    names = [
        "repositorySearchMenu",
        "repositorySearchInput",
        "repositorySearchBox",
        "repositorySearchResultArea",
        "repositorySearchEmptyState",
    ]
    objects = [root.findChild(QObject, name) for name in names]
    if any(item is None for item in objects):
        raise AssertionError(dict(zip(names, objects)))
    return objects


def _filtered_paths(menu) -> list[str]:
    paths = menu.property("filteredPaths")
    if hasattr(paths, "toVariant"):
        paths = paths.toVariant()
    return [str(path) for path in paths]


def _render_probe(output: Path) -> int:
    from PySide6.QtCore import QPointF
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    component, root = _create_scene(engine, use_in_window_popup=True)
    _pump(800)
    menu, search_input, search_box, result_area, _ = _scene_objects(root)
    search_input.setProperty("text", "prismqml")
    _pump(200)

    if _filtered_paths(menu) != ["D:/PrismQML/Gitora"]:
        raise AssertionError(_filtered_paths(menu))
    search_top = search_box.mapToScene(QPointF(0, 0)).y()
    search_bottom = search_top + search_box.height()
    result_top = result_area.mapToScene(QPointF(0, 0)).y()
    if search_bottom > result_top + 0.25:
        raise AssertionError(
            f"search overlaps results: {search_top=} {search_bottom=} {result_top=}"
        )

    image = root.grabWindow()
    if image.isNull() or not image.save(str(output), "PNG"):
        raise AssertionError("failed to save rendered repository search menu")
    print(
        f"{RENDER_MARKER} filtered={_filtered_paths(menu)} "
        f"search=({search_top},{search_bottom}) result_top={result_top} output={output}"
    )
    root.close()
    root.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


def _behavior_probe() -> int:
    from PySide6.QtCore import Q_ARG, QMetaObject, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import register_types

    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    component, root = _create_scene(engine, use_in_window_popup=False)
    _pump(200)
    menu, search_input, _, _, empty_state = _scene_objects(root)

    original_paths = _filtered_paths(menu)
    if len(original_paths) != 4:
        raise AssertionError(original_paths)
    search_input.setProperty("text", "GITORA")
    _pump(50)
    if _filtered_paths(menu) != ["D:/PrismQML/Gitora"]:
        raise AssertionError(_filtered_paths(menu))
    search_input.setProperty("text", "not-a-repository")
    _pump(50)
    if _filtered_paths(menu) != []:
        raise AssertionError(_filtered_paths(menu))
    if not empty_state.property("visible"):
        raise AssertionError("missing empty search state")
    if empty_state.property("text") != "没有匹配的仓库":
        raise AssertionError(empty_state.property("text"))
    search_input.setProperty("text", "")
    _pump(50)
    if _filtered_paths(menu) != original_paths:
        raise AssertionError(_filtered_paths(menu))

    selected: list[str] = []
    menu.pathSelected.connect(selected.append)
    search_input.setProperty("text", "minecraft")
    _pump(50)
    matches = _filtered_paths(menu)
    if len(matches) != 2:
        raise AssertionError(matches)
    invoked = QMetaObject.invokeMethod(
        menu,
        "activateIndex",
        Qt.ConnectionType.DirectConnection,
        Q_ARG("QVariant", 1),
    )
    if not invoked or selected != [matches[1]]:
        raise AssertionError({"invoked": invoked, "selected": selected, "matches": matches})

    print(f"{BEHAVIOR_MARKER} selected={selected[0]} restored={len(original_paths)}")
    root.close()
    root.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--behavior-probe":
        raise SystemExit(_behavior_probe())
    if len(sys.argv) == 3 and sys.argv[1] == "--render-probe":
        raise SystemExit(_render_probe(Path(sys.argv[2])))
    raise SystemExit(
        "usage: test_repository_search_menu_qml.py "
        "--behavior-probe | --render-probe OUTPUT"
    )
