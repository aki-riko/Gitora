# coding: utf-8
"""Windows taskbar/window icon bridge for the QML shell."""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QGuiApplication, QIcon

from app.common.logger import get_logger


_IMAGE_ICON = 1
_LR_LOAD_FROM_FILE = 0x00000010
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_GCLP_HICON = -14
_GCLP_HICONSM = -34
_SM_CXICON = 11
_SM_CYICON = 12
_SM_CXSMICON = 49
_SM_CYSMICON = 50


class WindowIconBridge(QObject):
    """Apply the app icon to Qt and native Windows icon slots."""

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._logger = get_logger(__name__)
        self._native_icon_handles: list[int] = []

    @Slot(QObject, str, result=bool)
    def applyWindowIcon(self, window: QObject, icon: str) -> bool:
        icon_path = self._resolve_icon_path(icon)
        if not icon_path:
            self._logger.warning("Window icon path is empty or unsupported: %r", icon)
            return False

        qicon = QIcon(icon_path)
        if qicon.isNull():
            self._logger.warning("Failed to load Qt window icon: %s", icon_path)
            return False

        app = QGuiApplication.instance()
        if app is not None:
            app.setWindowIcon(qicon)

        if window is not None and hasattr(window, "setIcon"):
            try:
                window.setIcon(qicon)
            except (AttributeError, TypeError, RuntimeError) as exc:
                self._logger.warning("Failed to set QWindow icon: %s", exc)

        ico_path = self._find_native_icon_path(icon_path)
        if sys.platform == "win32" and ico_path:
            return self._apply_windows_native_icon(window, ico_path)

        return True

    @staticmethod
    def _resolve_icon_path(icon: str) -> str:
        if not icon:
            return ""

        url = QUrl(icon)
        if url.isValid() and url.isLocalFile():
            return url.toLocalFile()

        if icon.startswith("qrc:") or icon.startswith(":/"):
            return icon

        return str(Path(icon).resolve())

    @staticmethod
    def _find_native_icon_path(icon_path: str) -> str:
        path = Path(icon_path)
        candidates = (
            [path] if path.suffix.lower() == ".ico" else [path.with_suffix(".ico")]
        )
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
        return ""

    def _apply_windows_native_icon(self, window: QObject, ico_path: str) -> bool:
        hwnd = self._window_handle(window)
        if hwnd == 0:
            return False

        user32 = ctypes.windll.user32
        self._configure_user32(user32)
        big_icon, small_icon = self._load_native_icon_pair(user32, ico_path)
        if not big_icon or not small_icon:
            self._logger.warning("Failed to load native icon from %s", ico_path)
            return False

        self._install_native_icons(user32, hwnd, big_icon, small_icon)
        self._native_icon_handles.extend([big_icon, small_icon])
        return True

    def _window_handle(self, window: QObject) -> int:
        if window is None or not hasattr(window, "winId"):
            self._logger.warning("Window object does not expose winId(); native icon skipped")
            return 0

        try:
            hwnd = int(window.winId())
        except (TypeError, ValueError, RuntimeError) as exc:
            self._logger.warning("Failed to obtain native window handle: %s", exc)
            return 0

        if hwnd == 0:
            self._logger.warning("Native window handle is empty; native icon skipped")
        return hwnd

    @staticmethod
    def _configure_user32(user32) -> None:
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.SendMessageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        user32.SendMessageW.restype = ctypes.c_void_p

    def _load_native_icon_pair(self, user32, ico_path: str) -> tuple[int, int]:
        big_icon = self._load_hicon(
            user32,
            ico_path,
            user32.GetSystemMetrics(_SM_CXICON),
            user32.GetSystemMetrics(_SM_CYICON),
            _IMAGE_ICON,
            _LR_LOAD_FROM_FILE,
        )
        small_icon = self._load_hicon(
            user32,
            ico_path,
            user32.GetSystemMetrics(_SM_CXSMICON),
            user32.GetSystemMetrics(_SM_CYSMICON),
            _IMAGE_ICON,
            _LR_LOAD_FROM_FILE,
        )
        return big_icon, small_icon

    @staticmethod
    def _install_native_icons(user32, hwnd: int, big_icon: int, small_icon: int) -> None:
        hwnd_p = ctypes.c_void_p(hwnd)
        user32.SendMessageW(
            hwnd_p,
            _WM_SETICON,
            ctypes.c_void_p(_ICON_BIG),
            ctypes.c_void_p(big_icon),
        )
        user32.SendMessageW(
            hwnd_p,
            _WM_SETICON,
            ctypes.c_void_p(_ICON_SMALL),
            ctypes.c_void_p(small_icon),
        )
        WindowIconBridge._set_class_icon(user32, hwnd_p, _GCLP_HICON, big_icon)
        WindowIconBridge._set_class_icon(user32, hwnd_p, _GCLP_HICONSM, small_icon)

    @staticmethod
    def _load_hicon(user32, ico_path: str, width: int, height: int, image_icon: int, flags: int) -> int:
        user32.LoadImageW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        user32.LoadImageW.restype = ctypes.c_void_p
        return int(user32.LoadImageW(None, ico_path, image_icon, width, height, flags) or 0)

    @staticmethod
    def _set_class_icon(user32, hwnd, index: int, icon_handle: int) -> None:
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            user32.SetClassLongPtrW.restype = ctypes.c_void_p
            user32.SetClassLongPtrW(hwnd, index, ctypes.c_void_p(icon_handle))
        else:
            user32.SetClassLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            user32.SetClassLongW.restype = ctypes.c_long
            user32.SetClassLongW(hwnd, index, icon_handle)
