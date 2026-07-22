# coding: utf-8
"""需要调用 Qt Quick 非 QML API 的渲染兼容层。"""

from PySide6.QtCore import QObject, Slot
from PySide6.QtQuick import QQuickItem


class QmlRenderBridge(QObject):
    """为 QML 组件提供受控的 Qt Quick 渲染开关。"""

    @Slot(QObject)
    def disableTextViewportCulling(self, item: QObject) -> None:
        """关闭长富文本在祖先视口内的按块剔除，避免滚动后缺行。"""
        if not isinstance(item, QQuickItem):
            return
        item.setFlag(QQuickItem.Flag.ItemObservesViewport, False)
