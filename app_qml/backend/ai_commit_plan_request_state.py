# coding: utf-8
"""AI 提交规划异步请求的线程安全状态。"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Protocol

from app.common.ai_commit_context import ChangeContextCollector, SnapshotCollectionError
from app.common.ai_commit_models import ChangeSnapshot, PlannerRequest
from app.common.ai_commit_provider import ModelProvider
from app.common.ai_commit_settings import AiCommitSettings


class PlannerRuntime(Protocol):
    def planning_settings(self) -> AiCommitSettings: ...

    def create_provider_for(self, settings: AiCommitSettings) -> ModelProvider: ...


@dataclass(frozen=True)
class PreparedPlanRequest:
    request_id: str
    repo_path: str
    snapshot: ChangeSnapshot
    request: PlannerRequest
    settings: AiCommitSettings
    is_remote: bool


class PlanRequestState:
    """原子管理请求序号、取消事件、busy 与待发送上下文。"""

    def __init__(
        self,
        current_repo: Callable[[], str],
        busy_changed: Callable[[], None],
    ):
        self._current_repo = current_repo
        self._busy_changed = busy_changed
        self._serial = 0
        self._prepared: PreparedPlanRequest | None = None
        self._cancel_event = threading.Event()
        self._busy = False
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    @property
    def prepared(self) -> PreparedPlanRequest | None:
        with self._lock:
            return self._prepared

    @property
    def has_prepared(self) -> bool:
        with self._lock:
            return self._prepared is not None

    def start(self, clear_prepared: bool) -> tuple[int, threading.Event]:
        with self._lock:
            self._serial += 1
            self._cancel_event.set()
            self._cancel_event = threading.Event()
            if clear_prepared:
                self._prepared = None
            self._busy = True
            result = self._serial, self._cancel_event
        self._busy_changed()
        return result

    def cancel(self) -> bool:
        """废弃当前请求，并返回 busy 是否发生变化。"""
        with self._lock:
            self._serial += 1
            self._cancel_event.set()
            self._cancel_event = threading.Event()
            self._prepared = None
            was_busy = self._busy
            self._busy = False
        if was_busy:
            self._busy_changed()
        return was_busy

    def set_busy_if_current(self, serial: int, value: bool) -> bool:
        """仅更新当前请求，并返回属性是否发生变化。"""
        with self._lock:
            if serial != self._serial or self._busy == value:
                return False
            self._busy = value
        self._busy_changed()
        return True

    def is_serial_current(self, serial: int) -> bool:
        with self._lock:
            return serial == self._serial and not self._cancel_event.is_set()

    def is_current(
        self, serial: int, repo: str, event: threading.Event
    ) -> bool:
        with self._lock:
            current = serial == self._serial and not event.is_set()
        return current and repo == self._current_repo()

    def store_prepared_if_current(
        self,
        serial: int,
        repo: str,
        event: threading.Event,
        prepared: PreparedPlanRequest,
    ) -> bool:
        with self._lock:
            if (
                serial != self._serial
                or event.is_set()
                or repo != self._current_repo()
            ):
                return False
            self._prepared = prepared
            return True

    def take_prepared(self, request_id: str) -> PreparedPlanRequest | None:
        with self._lock:
            prepared = self._prepared
            if prepared is None or prepared.request_id != request_id:
                return None
            self._prepared = None
            return prepared

    def cancel_prepared(self, request_id: str) -> None:
        with self._lock:
            if self._prepared and self._prepared.request_id == request_id:
                self._prepared = None


def ensure_plan_fingerprint(
    collector: ChangeContextCollector,
    prepared: PreparedPlanRequest,
) -> None:
    current = collector.workspace_fingerprint(prepared.repo_path)
    if current != prepared.snapshot.workspace_fingerprint:
        raise SnapshotCollectionError("工作区已变化，请重新规划")
