# coding: utf-8
"""需要调用 Qt Quick 非 QML API 的渲染兼容层。"""

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickItem

from app.common.logger import get_logger


logger = get_logger("Gitora")


class QmlRenderBridge(QObject):
    """为 QML 组件提供受控的 Qt Quick 渲染开关。"""

    @Slot(QObject)
    def disableTextViewportCulling(self, item: QObject) -> None:
        """关闭长富文本在祖先视口内的按块剔除，避免滚动后缺行。"""
        if not isinstance(item, QQuickItem):
            return
        item.setFlag(QQuickItem.Flag.ItemObservesViewport, False)

    @Slot(result=int)
    def topLevelWindowCount(self) -> int:
        """进程顶层窗口数量，供停顿观测区分窗口/资源累积与业务主线程占用。"""
        return len(QGuiApplication.topLevelWindows())

    @Slot(str)
    def logStallTrace(self, message: str) -> None:
        """把 QML 侧观测写入应用日志：QML 的 console 输出不落 Gitora 日志文件。"""
        logger.info(str(message))
