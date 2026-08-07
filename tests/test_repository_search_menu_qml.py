# coding: utf-8
"""仓库搜索弹层的过滤、路径映射与真实 QML 渲染测试。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RENDER_MARKER = "[REPOSITORY_SEARCH_MENU_RENDER]"
BEHAVIOR_MARKER = "[REPOSITORY_SEARCH_MENU_BEHAVIOR]"
NATIVE_FIRST_CLICK_MARKER = "[REPOSITORY_SEARCH_MENU_NATIVE_FIRST_CLICK]"
PROBE_SOURCE = """
import QtQuick
import QtQuick.Window
import PrismQML as Fluent
import "components"

Window {
    id: root
    width: 820
    height: 620
    visible: true
    color: Fluent.Enums.backgroundColor
    property int mainClickCount: 0
    property bool useScreenshotPaths: false

    function prepareScreenshotPaths() {
        menu.prepareForOpen([
            "D:/MinecraftProject/mojin",
            "B:/Minecraft/Addons和modApi/已冻结策划JOJO",
            "B:/Minecraft/Addons和modApi/已完成作品(新)/LuckyWorld",
            "B:/Minecraft/Addons和modApi/已完成作品(新)/MailSystem",
            "D:/PrismQML/AeroMount",
            "L:/home/Aquila/Minecraft/Addons和modApi/已完成作品(新)/MailSystem",
            "L:/home/Aquila/Minecraft/Addons和modApi/已完成作品(新)/LuckyWorld",
            "L:/home/Aquila/Minecraft/Addons和modApi/已冻结策划JOJO"
        ])
    }

    Fluent.Button {
        id: trigger
        objectName: "repositoryMenuTrigger"
        x: Fluent.Enums.spacing.xl
        y: Fluent.Enums.spacing.xl
        width: 180
        text: "打开"
        icon: Fluent.Enums.icon.folder
        feature: Fluent.Enums.button.feature_split
        menu: menu
        onClicked: root.mainClickCount += 1
        onMenuAboutToOpen: {
            if (root.useScreenshotPaths) {
                root.prepareScreenshotPaths()
            } else {
                menu.prepareForOpen([
                    "D:/API/new-api",
                    "D:/MinecraftProject/mojin",
                    "D:/API/kiro_rs",
                    "D:/PrismQML/Gitora",
                    "B:/Minecraft/Addons和modApi/已完成作品(新)/LuckyWorld"
                ])
            }
        }
    }

    RepositorySearchMenu {
        id: menu
        objectName: "repositorySearchMenu"
        useInWindowPopup: UseInWindowPopup
        useQtPopupWindow: !UseInWindowPopup
        pathFormatter: function(path) { return path }
    }

}
""".encode("utf-8")


def _probe_environment(*, native_window: bool = False) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    if native_window:
        environment.pop("QT_QPA_PLATFORM", None)
        environment.pop("QT_QUICK_BACKEND", None)
    else:
        environment.update(
            {
                "QT_QPA_PLATFORM": "offscreen",
                "QT_QUICK_BACKEND": "software",
            }
        )
    windows_root = environment.get("WINDIR", "").strip()
    font_directory = Path(windows_root) / "Fonts"
    if os.name == "nt" and font_directory.is_dir():
        environment["QT_QPA_FONTDIR"] = str(font_directory)
    return environment


def _run_probe(
    mode: str,
    output: Path | None = None,
    *,
    native_window: bool = False,
) -> subprocess.CompletedProcess[str]:
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
        env=_probe_environment(native_window=native_window),
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
    assert "[WARNING]" not in result.stdout, diagnostic
    assert "[ERROR]" not in result.stdout, diagnostic
    assert result.stderr == "", diagnostic


@pytest.mark.skipif(os.name != "nt", reason="需要 Windows 原生窗口事件循环")
def test_repository_search_menu_native_first_click_switches_repository() -> None:
    result = _run_probe("--native-first-click-probe", native_window=True)
    diagnostic = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, diagnostic
    assert NATIVE_FIRST_CLICK_MARKER in result.stdout, diagnostic
    assert "[WARNING]" not in result.stdout, diagnostic
    assert "[ERROR]" not in result.stdout, diagnostic
    assert result.stderr == "", diagnostic


def test_repository_search_menu_uses_in_window_popup() -> None:
    source = (
        ROOT / "app_qml" / "qml" / "components" / "RepositorySearchMenu.qml"
    ).read_text(encoding="utf-8")
    assert "useInWindowPopup: true" in source
    assert "useQtPopupWindow: false" in source


def test_repository_search_menu_renders_results_without_clipping() -> None:
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


def _trigger(root):
    from PySide6.QtCore import QObject

    trigger = root.findChild(QObject, "repositoryMenuTrigger")
    if trigger is None:
        raise AssertionError("missing repository split trigger")
    return trigger


def _click_trigger(root, trigger, arrow: bool) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest

    x = trigger.width() - 16 if arrow else 36
    point = trigger.mapToScene(QPointF(x, trigger.height() / 2)).toPoint()
    QTest.mouseClick(
        root,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        point,
    )
    _pump(100)


def _wait_for(predicate, timeout_ms: int = 1000) -> bool:
    elapsed = 0
    while elapsed < timeout_ms:
        if predicate():
            return True
        _pump(5)
        elapsed += 5
    return bool(predicate())


def _click_result_once(menu, index: int) -> int:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtTest import QTest

    object_name = f"repositorySearchResult-{index}"
    popup_content = menu.findChild(QQuickItem, "_popupContent")
    if popup_content is None:
        raise AssertionError("missing repository popup content")

    def find_result_item():
        pending = list(popup_content.childItems())
        while pending:
            item = pending.pop()
            if item.objectName() == object_name:
                return item
            pending.extend(item.childItems())
        return None

    if not _wait_for(lambda: find_result_item() is not None):
        raise AssertionError(f"missing repository result delegate: {object_name}")
    if not _wait_for(
        lambda: abs(
            float(menu.property("_clipHeight"))
            - float(menu.property("popupHeight"))
        ) < 0.25
    ):
        raise AssertionError("repository popup animation did not settle")
    item = find_result_item()
    clicked_events: list[bool] = []
    item.clicked.connect(lambda: clicked_events.append(True))
    popup_window = item.window()
    if popup_window is None:
        raise AssertionError("repository result delegate has no window")
    click_position = item.mapToScene(
        QPointF(item.width() / 2, item.height() / 2)
    ).toPoint()
    QTest.mouseClick(
        popup_window,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        click_position,
    )
    _pump(50)
    return len(clicked_events)


def _assert_screenshot_search_geometry(menu, search_input, result_area) -> tuple[float, float]:
    from PySide6.QtCore import QPointF
    from PySide6.QtQuick import QQuickItem

    search_input.setProperty("text", "moj")
    _pump(100)
    if _filtered_paths(menu) != ["D:/MinecraftProject/mojin"]:
        raise AssertionError(_filtered_paths(menu))
    popup_content = menu.findChild(QQuickItem, "_popupContent")
    if popup_content is None:
        raise AssertionError("missing popup content")
    result_bottom = result_area.mapToItem(
        popup_content, QPointF(0, result_area.height())
    ).y()
    content_height = popup_content.height()
    if result_bottom > content_height + 0.25:
        raise AssertionError(
            f"results clipped: {result_bottom=} {content_height=}"
        )
    popup_height = float(menu.property("popupHeight"))
    clip_height = float(menu.property("_clipHeight"))
    if abs(clip_height - popup_height) > 0.25:
        raise AssertionError(
            f"shadow geometry stale: {clip_height=} {popup_height=}"
        )
    return result_bottom, content_height


def _render_probe(output: Path) -> int:
    from PySide6.QtCore import QPointF
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import configure_qml_environment, register_types
    from prismqml.python.core import install_qt_message_handler

    configure_qml_environment()
    install_qt_message_handler()
    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    component, root = _create_scene(engine, use_in_window_popup=True)
    root.requestActivate()
    _pump(100)
    root.setProperty("useScreenshotPaths", True)
    _click_trigger(root, _trigger(root), arrow=True)
    _pump(700)
    menu, search_input, search_box, result_area, _ = _scene_objects(root)
    result_bottom, content_height = _assert_screenshot_search_geometry(
        menu, search_input, result_area
    )
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
        f"{RENDER_MARKER} matches=1 search=({search_top},{search_bottom}) "
        f"result_top={result_top} result_bottom={result_bottom} "
        f"content_height={content_height} output={output}"
    )
    root.close()
    root.deleteLater()
    component.deleteLater()
    engine.deleteLater()
    app.processEvents()
    return 0


def _behavior_probe(*, first_click_only: bool = False) -> int:
    from PySide6.QtCore import Q_ARG, QMetaObject, Qt
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtWidgets import QApplication
    from prismqml import configure_qml_environment, register_types
    from prismqml.python.core import install_qt_message_handler

    configure_qml_environment()
    install_qt_message_handler()
    app = QApplication([str(Path(__file__))])
    engine = QQmlApplicationEngine()
    register_types(engine)
    component, root = _create_scene(engine, use_in_window_popup=True)
    root.requestActivate()
    _pump(100)
    menu, search_input, _, _, empty_state = _scene_objects(root)
    trigger = _trigger(root)
    selected: list[str] = []
    menu.pathSelected.connect(selected.append)

    _click_trigger(root, trigger, arrow=False)
    if root.property("mainClickCount") != 1 or menu.property("isOpen"):
        raise AssertionError("split main action opened the repository menu")
    _click_trigger(root, trigger, arrow=True)
    if root.property("mainClickCount") != 1 or not menu.property("isOpen"):
        raise AssertionError("split arrow did not open the repository menu")

    if first_click_only:
        clicked_count = _click_result_once(menu, 0)
        if clicked_count != 1 or selected != ["D:/API/new-api"]:
            raise AssertionError(
                {
                    "first_click_selected": selected,
                    "delegate_clicked_count": clicked_count,
                }
            )
        print(f"{NATIVE_FIRST_CLICK_MARKER} selected={selected[0]}")
        return 0

    original_paths = _filtered_paths(menu)
    if len(original_paths) != 5:
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

    selected.clear()
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
    if len(sys.argv) == 2 and sys.argv[1] == "--native-first-click-probe":
        raise SystemExit(_behavior_probe(first_click_only=True))
    if len(sys.argv) == 3 and sys.argv[1] == "--render-probe":
        raise SystemExit(_render_probe(Path(sys.argv[2])))
    raise SystemExit(
        "usage: test_repository_search_menu_qml.py "
        "--behavior-probe | --native-first-click-probe | --render-probe OUTPUT"
    )
