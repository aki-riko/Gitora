# coding: utf-8
import unittest
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtQuick import QQuickItem

from app_qml.backend.qml_render_bridge import QmlRenderBridge


ROOT = Path(__file__).resolve().parents[1]


class QmlRenderBridgeTest(unittest.TestCase):
    def test_disable_text_viewport_culling_clears_qt_item_flag(self) -> None:
        item = QQuickItem()
        item.setFlag(QQuickItem.Flag.ItemObservesViewport, True)

        QmlRenderBridge().disableTextViewportCulling(item)

        self.assertFalse(
            item.flags() & QQuickItem.Flag.ItemObservesViewport
        )

    def test_disable_text_viewport_culling_ignores_non_items(self) -> None:
        QmlRenderBridge().disableTextViewportCulling(QObject())

    def test_main_registers_render_bridge_for_qml(self) -> None:
        source = (ROOT / "app_qml" / "main_qml.py").read_text(encoding="utf-8")

        self.assertIn("from app_qml.backend.qml_render_bridge import QmlRenderBridge", source)
        self.assertIn("qml_render_bridge = QmlRenderBridge()", source)
        self.assertIn(
            'ctx.setContextProperty("QmlRenderBridge", qml_render_bridge)', source
        )


if __name__ == "__main__":
    unittest.main()
