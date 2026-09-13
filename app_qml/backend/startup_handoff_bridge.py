# coding: utf-8
"""Expose the FastSplash reveal handoff to QML without opening native UI early."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class StartupHandoffBridge(QObject):
    """Emit once when FastSplash has completed its native handoff."""

    startupHandoffReady = Signal()

    def __init__(self, controller: object, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(16)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

    def _poll(self) -> None:
        if not bool(getattr(self._controller, "_handoff_done", False)):
            return
        self._poll_timer.stop()
        self.startupHandoffReady.emit()
