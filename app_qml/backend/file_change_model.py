# coding: utf-8
"""QML 变更文件列表模型。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    Property,
    Qt,
    Signal,
    Slot,
)

from app.common.git_service import FileChange


class FileChangeListModel(QAbstractListModel):
    """一次性刷新、供 QML ListView 直接消费的变更列表模型。"""

    PathRole = Qt.ItemDataRole.UserRole + 1
    StatusRole = PathRole + 1
    StatusTextRole = PathRole + 2
    StagedRole = PathRole + 3

    countChanged = Signal()

    _ROLE_NAMES = {
        PathRole: QByteArray(b"path"),
        StatusRole: QByteArray(b"status"),
        StatusTextRole: QByteArray(b"statusText"),
        StagedRole: QByteArray(b"staged"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[FileChange] = []

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None

        item = self._items[index.row()]
        if role == self.PathRole:
            return item.path
        if role == self.StatusRole:
            return item.status.value
        if role == self.StatusTextRole:
            return item.status_text
        if role == self.StagedRole:
            return item.staged
        return None

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802
        return self._ROLE_NAMES

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._items)

    def replace(self, items: Sequence[FileChange]) -> None:
        """在 GUI 线程一次性替换模型，避免 QML 逐条插入触发布局。"""
        new_items = list(items)
        old_count = len(self._items)
        self.beginResetModel()
        self._items = new_items
        self.endResetModel()
        if len(new_items) != old_count:
            self.countChanged.emit()

    @Slot()
    def clear(self) -> None:
        if not self._items:
            return
        self.beginResetModel()
        self._items = []
        self.endResetModel()
        self.countChanged.emit()

    @Slot(str, bool, result=bool)
    def contains(self, path: str, staged: bool) -> bool:
        return any(item.path == path and item.staged == staged for item in self._items)
