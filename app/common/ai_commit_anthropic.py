# coding: utf-8
"""Anthropic Messages API 提交规划提供方。"""
from __future__ import annotations

from threading import Event
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from .ai_commit_http import (
    _build_json_schema_prompt,
    _extract_model_ids,
    _validate_api_key,
    _validate_remote_endpoint,
    HttpJsonClient,
    HttpProviderConfig,
    HttpProviderError,
    OllamaProvider,
)
from .ai_commit_models import PlannerRequest
from .ai_commit_provider import ModelProvider
from .ai_commit_schema import build_user_input


class AnthropicMessagesProvider(ModelProvider):
    """远程 Anthropic Messages API 提供方。"""

    _max_tokens = 8192

    def __init__(self, config: HttpProviderConfig):
        self.config = config
        self._endpoint, self._models_url = self._resolve_endpoints(config.endpoint)
        self._client = HttpJsonClient(
            config.timeout_seconds, config.max_response_chars
        )

    @property
    def provider_id(self) -> str:
        return "anthropic"

    def generate_plan(
        self, request: PlannerRequest, cancel_event: Event | None = None
    ) -> Mapping[str, Any]:
        OllamaProvider._check_cancelled(cancel_event)
        if not self.config.model:
            raise HttpProviderError("未配置远程模型名")
        response = self._client.request(
            "POST",
            self._endpoint,
            {
                "model": self.config.model,
                "max_tokens": self._max_tokens,
                "system": _build_json_schema_prompt(request),
                "messages": [{
                    "role": "user",
                    "content": build_user_input(request),
                }],
            },
            self._headers(),
        )
        OllamaProvider._check_cancelled(cancel_event)
        return OllamaProvider._parse_plan_text(self._extract_text(response))

    def list_models(self) -> tuple[str, ...]:
        response = self._client.request(
            "GET", self._models_url, headers=self._headers()
        )
        return _extract_model_ids(response, "Anthropic")

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": _validate_api_key(self.config.api_key),
            "anthropic-version": "2023-06-01",
        }

    @staticmethod
    def _resolve_endpoints(value: str) -> tuple[str, str]:
        endpoint = _validate_remote_endpoint(value)
        parsed = urlsplit(endpoint)
        path = parsed.path.rstrip("/")
        if path.endswith("/messages"):
            base_path = path.removesuffix("/messages")
        elif path.endswith("/v1"):
            base_path = path
        else:
            base_path = path + "/v1"
        messages_path = base_path + "/messages"
        models_path = base_path + "/models"
        messages_url = urlunsplit(
            (parsed.scheme, parsed.netloc, messages_path, "", "")
        )
        models_url = urlunsplit(
            (parsed.scheme, parsed.netloc, models_path, "", "")
        )
        return messages_url, models_url

    @staticmethod
    def _extract_text(response: Mapping[str, Any]) -> str:
        content = response.get("content")
        if isinstance(content, list):
            texts = [
                part["text"]
                for part in content
                if (
                    isinstance(part, Mapping)
                    and part.get("type") == "text"
                    and isinstance(part.get("text"), str)
                )
            ]
            if texts:
                return "".join(texts)
        raise HttpProviderError(
            "Anthropic Messages API 响应缺少 content[].text"
        )
