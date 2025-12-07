# coding:utf-8
"""
虚拟滚动文件列表 - 使用QListView实现高性能文件变更列表
支持上千个文件不卡顿
"""
from PySide6.QtCore import Qt, Signal, QModelIndex, QSize, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QListView, QStyledItemDelegate, QStyle, QStyleOptionViewItem,
    QApplication
)

from qfluentwidgets import (
    FluentIcon, isDarkTheme, themeColor
)
from qfluentwidgetspro import RoundListWidget

from app.common.git_service import FileChange, FileStatus
from app.common.logger import get_logger

logger = get_logger("VirtualFileList")


# 自定义数据角色
class FileRole:
    PathRole = Qt.ItemDataRole.UserRole + 1
    StatusRole = Qt.ItemDataRole.UserRole + 2
    StagedRole = Qt.ItemDataRole.UserRole + 3
    StatusTextRole = Qt.ItemDataRole.UserRole + 4
    FileChangeRole = Qt.ItemDataRole.UserRole + 5


class FileChangeDelegate(QStyledItemDelegate):
    """文件变更项委托 - 绘制文件卡片样式"""
    
    # 按钮区域常量
    ITEM_HEIGHT = 56
    BUTTON_SIZE = 28
    BUTTON_MARGIN = 8
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hoverRow = -1
        self.pressedRow = -1
        self.selectedRows = set()
        self._hover_button = None  # 'stage' or 'discard'
        
    def setHoverRow(self, row: int):
        self.hoverRow = row
        
    def setPressedRow(self, row: int):
        self.pressedRow = row
    
    def setSelectedRows(self, indexes):
        """设置选中行 - RoundListWidget 需要此方法"""
        self.selectedRows.clear()
        for index in indexes:
            self.selectedRows.add(index.row())
            if index.row() == self.pressedRow:
                self.pressedRow = -1
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 获取数据
        path = index.data(FileRole.PathRole)
        status = index.data(FileRole.StatusRole)
        staged = index.data(FileRole.StagedRole)
        status_text = index.data(FileRole.StatusTextRole)
        
        if not path:
            painter.restore()
            return
        
        rect = option.rect
        is_dark = isDarkTheme()
        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_hover = option.state & QStyle.StateFlag.State_MouseOver
        
        # 背景
        if is_selected:
            bg_color = QColor(themeColor().red(), themeColor().green(), themeColor().blue(), 40)
        elif is_hover:
            bg_color = QColor(255, 255, 255, 20) if is_dark else QColor(0, 0, 0, 10)
        else:
            bg_color = QColor(255, 255, 255, 10) if is_dark else QColor(255, 255, 255, 255)
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect.adjusted(4, 2, -4, -2), 8, 8)
        
        # 边框
        if is_selected:
            painter.setPen(QPen(themeColor(), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(4, 2, -4, -2), 8, 8)
        
        # 状态图标
        icon_rect = QRect(rect.left() + 16, rect.top() + (rect.height() - 20) // 2, 20, 20)
        status_icon = self._get_status_icon(status)
        if status_icon:
            status_icon.icon().paint(painter, icon_rect)
        
        # 文件路径
        text_left = icon_rect.right() + 12
        text_width = rect.width() - text_left - 80  # 留空间给按钮
        
        path_rect = QRect(text_left, rect.top() + 10, text_width, 20)
        text_color = QColor(255, 255, 255) if is_dark else QColor(0, 0, 0)
        painter.setPen(text_color)
        
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        
        # 裁剪过长的路径
        fm = QFontMetrics(font)
        elided_path = fm.elidedText(path, Qt.TextElideMode.ElideMiddle, text_width)
        painter.drawText(path_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_path)
        
        # 状态文本
        status_rect = QRect(text_left, rect.top() + 30, text_width, 16)
        status_color = self._get_status_color(status)
        painter.setPen(status_color)
        font.setPointSize(9)
        painter.setFont(font)
        
        display_status = status_text
        if staged:
            display_status += " " + QApplication.translate("VirtualFileList", "(已暂存)")
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, display_status)
        
        # 操作按钮区域（只在hover时显示）
        if is_hover or is_selected:
            btn_y = rect.top() + (rect.height() - self.BUTTON_SIZE) // 2
            
            # 暂存/取消暂存按钮
            stage_btn_rect = QRect(
                rect.right() - self.BUTTON_MARGIN - self.BUTTON_SIZE * 2 - 4,
                btn_y, self.BUTTON_SIZE, self.BUTTON_SIZE
            )
            self._draw_button(painter, stage_btn_rect, 
                             FluentIcon.REMOVE if staged else FluentIcon.ADD,
                             is_dark)
            
            # 放弃修改按钮（仅未暂存时显示）
            if not staged:
                discard_btn_rect = QRect(
                    rect.right() - self.BUTTON_MARGIN - self.BUTTON_SIZE,
                    btn_y, self.BUTTON_SIZE, self.BUTTON_SIZE
                )
                self._draw_button(painter, discard_btn_rect, FluentIcon.DELETE, is_dark)
        
        painter.restore()
    
    def _draw_button(self, painter: QPainter, rect: QRect, icon: FluentIcon, is_dark: bool):
        """绘制按钮"""
        # 按钮背景
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30) if is_dark else QColor(0, 0, 0, 10))
        painter.drawRoundedRect(rect, 6, 6)
        
        # 图标
        icon_size = 16
        icon_rect = QRect(
            rect.left() + (rect.width() - icon_size) // 2,
            rect.top() + (rect.height() - icon_size) // 2,
            icon_size, icon_size
        )
        icon.icon().paint(painter, icon_rect)
    
    def _get_status_icon(self, status: FileStatus) -> FluentIcon:
        """获取状态图标"""
        icon_map = {
            FileStatus.MODIFIED: FluentIcon.EDIT,
            FileStatus.ADDED: FluentIcon.ADD,
            FileStatus.DELETED: FluentIcon.DELETE,
            FileStatus.RENAMED: FluentIcon.SYNC,
            FileStatus.COPIED: FluentIcon.COPY,
            FileStatus.UNTRACKED: FluentIcon.QUESTION,
        }
        return icon_map.get(status, FluentIcon.DOCUMENT)
    
    def _get_status_color(self, status: FileStatus) -> QColor:
        """获取状态颜色"""
        color_map = {
            FileStatus.MODIFIED: QColor(255, 152, 0),    # 橙色
            FileStatus.ADDED: QColor(76, 175, 80),       # 绿色
            FileStatus.DELETED: QColor(244, 67, 54),     # 红色
            FileStatus.RENAMED: QColor(33, 150, 243),    # 蓝色
            FileStatus.COPIED: QColor(156, 39, 176),     # 紫色
            FileStatus.UNTRACKED: QColor(158, 158, 158), # 灰色
        }
        return color_map.get(status, QColor(158, 158, 158))
    
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(option.rect.width(), self.ITEM_HEIGHT)
    
    def getButtonAtPos(self, pos: QPoint, rect: QRect, staged: bool) -> str:
        """获取点击位置的按钮类型"""
        btn_y = rect.top() + (rect.height() - self.BUTTON_SIZE) // 2
        
        # 暂存按钮
        stage_btn_rect = QRect(
            rect.right() - self.BUTTON_MARGIN - self.BUTTON_SIZE * 2 - 4,
            btn_y, self.BUTTON_SIZE, self.BUTTON_SIZE
        )
        if stage_btn_rect.contains(pos):
            return 'stage'
        
        # 放弃按钮
        if not staged:
            discard_btn_rect = QRect(
                rect.right() - self.BUTTON_MARGIN - self.BUTTON_SIZE,
                btn_y, self.BUTTON_SIZE, self.BUTTON_SIZE
            )
            if discard_btn_rect.contains(pos):
                return 'discard'
        
        return None


class VirtualFileList(RoundListWidget):
    """虚拟滚动文件列表"""
    
    stageClicked = Signal(str, bool)   # 文件路径, 是否暂存
    discardClicked = Signal(str)       # 文件路径
    fileSelected = Signal(str, bool)   # 文件路径, 是否已暂存
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._delegate = FileChangeDelegate(self)
        self.setItemDelegate(self._delegate)
        
        # 设置属性
        self.setMouseTracking(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 连接信号
        self.clicked.connect(self._on_item_clicked)
        self.currentItemChanged.connect(self._on_current_changed)
        
        # 存储文件变更数据
        self._file_changes: list[FileChange] = []
    
    def setFileChanges(self, changes: list[FileChange]):
        """设置文件变更列表"""
        self._file_changes = changes
        self.clear()
        
        from PySide6.QtWidgets import QListWidgetItem
        
        for change in changes:
            item = QListWidgetItem()
            item.setData(FileRole.PathRole, change.path)
            item.setData(FileRole.StatusRole, change.status)
            item.setData(FileRole.StagedRole, change.staged)
            item.setData(FileRole.StatusTextRole, change.status_text)
            item.setData(FileRole.FileChangeRole, change)
            item.setSizeHint(QSize(self.width(), FileChangeDelegate.ITEM_HEIGHT))
            self.addItem(item)
    
    def _on_item_clicked(self, index: QModelIndex):
        """处理点击事件"""
        if not index.isValid():
            return
        
        item = self.item(index.row())
        if not item:
            return
        
        path = item.data(FileRole.PathRole)
        staged = item.data(FileRole.StagedRole)
        
        # 检查是否点击了按钮
        pos = self.viewport().mapFromGlobal(QApplication.instance().overrideCursor().pos() if QApplication.instance().overrideCursor() else self.cursor().pos())
        rect = self.visualRect(index)
        button = self._delegate.getButtonAtPos(pos, rect, staged)
        
        if button == 'stage':
            self.stageClicked.emit(path, not staged)
        elif button == 'discard':
            self.discardClicked.emit(path)
        else:
            # 选中文件
            self.fileSelected.emit(path, staged)
    
    def _on_current_changed(self, current, previous):
        """当前项改变"""
        if current:
            path = current.data(FileRole.PathRole)
            staged = current.data(FileRole.StagedRole)
            if path:
                self.fileSelected.emit(path, staged)
    
    def mousePressEvent(self, event):
        """鼠标按下事件 - 检测按钮点击"""
        index = self.indexAt(event.pos())
        if index.isValid():
            item = self.item(index.row())
            if item:
                staged = item.data(FileRole.StagedRole)
                rect = self.visualRect(index)
                button = self._delegate.getButtonAtPos(event.pos(), rect, staged)
                
                if button == 'stage':
                    path = item.data(FileRole.PathRole)
                    self.stageClicked.emit(path, not staged)
                    return
                elif button == 'discard':
                    path = item.data(FileRole.PathRole)
                    self.discardClicked.emit(path)
                    return
        
        super().mousePressEvent(event)
    
    def getFileChanges(self) -> list[FileChange]:
        """获取所有文件变更"""
        return self._file_changes
    
    def getSelectedFiles(self) -> list[str]:
        """获取选中的文件路径"""
        paths = []
        for item in self.selectedItems():
            path = item.data(FileRole.PathRole)
            if path:
                paths.append(path)
        return paths
