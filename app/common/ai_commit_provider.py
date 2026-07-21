# coding: utf-8
"""AI 提交规划器的模型提供方协议。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Event
from typing import Any, Mapping

from .ai_commit_models import PlannerRequest


class ProviderCancelledError(RuntimeError):
    """用户在模型返回前取消了请求。"""


class ModelProvider(ABC):
    """模型提供方只生成结构化数据，不接触 Git 写操作。"""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_plan(
        self, request: PlannerRequest, cancel_event: Event | None = None
    ) -> Mapping[str, Any]:
        raise NotImplementedError


class StaticModelProvider(ModelProvider):
    """测试和离线特征化使用的固定响应提供方。"""

    def __init__(self, response: Mapping[str, Any], provider_id: str = "static"):
        self._response = dict(response)
        self._provider_id = provider_id
        self.requests: list[PlannerRequest] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def generate_plan(
        self, request: PlannerRequest, cancel_event: Event | None = None
    ) -> Mapping[str, Any]:
        if cancel_event is not None and cancel_event.is_set():
            raise ProviderCancelledError("请求已取消")
        self.requests.append(request)
        return dict(self._response)
