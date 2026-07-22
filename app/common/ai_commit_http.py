# coding: utf-8
"""基于已核对官方接口的远程 Responses 与本地 Ollama 提供方。"""
from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from threading import Event
from typing import Any, Mapping
from urllib.parse import urlsplit

from .ai_commit_models import PlannerRequest
from .ai_commit_provider import ModelProvider, ProviderCancelledError
from .ai_commit_schema import SYSTEM_INSTRUCTIONS, build_plan_schema, build_user_input


class HttpProviderError(RuntimeError):
    """不包含请求正文或密钥的模型连接错误。"""


@dataclass(frozen=True)
class HttpProviderConfig:
    endpoint: str
    model: str
    api_key: str
    timeout_seconds: int
    max_response_chars: int


def endpoint_requires_remote_consent(endpoint: str) -> bool:
    """仅把明确的本机回环地址视为无需远程发送确认。"""
    try:
        hostname = urlsplit(endpoint.strip()).hostname
    except ValueError:
        return True
    if not hostname:
        return True
    normalized = hostname.rstrip(".").casefold()
    if normalized == "localhost":
        return False
    try:
        return not ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return True


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """拒绝自动重定向，避免 HTTPS 端点被降级或转向其他主机。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpJsonClient:
    def __init__(
        self,
        timeout_seconds: int,
        max_response_chars: int,
        opener: Any | None = None,
        bypass_proxy: bool = False,
    ):
        if timeout_seconds <= 0 or max_response_chars <= 0:
            raise ValueError("网络限制必须为正整数")
        self.timeout_seconds = timeout_seconds
        self.max_response_chars = max_response_chars
        if opener is not None:
            self._opener = opener
        else:
            handlers = [_NoRedirectHandler()]
            if bypass_proxy:
                handlers.insert(0, urllib.request.ProxyHandler({}))
            self._opener = urllib.request.build_opener(*handlers)

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]:
        body = None
        request_headers = {"Accept": "application/json", **dict(headers or {})}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url, data=body, headers=request_headers, method=method
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_chars + 1)
        except urllib.error.HTTPError as exc:
            if exc.fp is not None:
                exc.close()
            raise HttpProviderError(f"模型服务返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise HttpProviderError(
                f"无法连接模型服务（{type(exc.reason).__name__}）"
            ) from exc
        except TimeoutError as exc:
            raise HttpProviderError("模型服务请求超时") from exc
        if len(raw) > self.max_response_chars:
            raise HttpProviderError("模型响应超过配置上限")
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HttpProviderError("模型服务返回的不是有效 JSON") from exc
        if not isinstance(parsed, Mapping):
            raise HttpProviderError("模型服务响应必须是 JSON 对象")
        return parsed


class OllamaProvider(ModelProvider):
    def __init__(self, config: HttpProviderConfig):
        self.config = config
        self._base_url = self._validate_base_url(config.endpoint)
        self._client = HttpJsonClient(
            config.timeout_seconds,
            config.max_response_chars,
            bypass_proxy=not endpoint_requires_remote_consent(self._base_url),
        )

    @property
    def provider_id(self) -> str:
        return "ollama"

    def generate_plan(
        self, request: PlannerRequest, cancel_event: Event | None = None
    ) -> Mapping[str, Any]:
        self._check_ready(cancel_event)
        response = self._client.request(
            "POST",
            self._base_url + "/api/chat",
            {
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user", "content": build_user_input(request)},
                ],
                "stream": False,
                "think": False,
                "format": build_plan_schema(request),
            },
        )
        self._check_cancelled(cancel_event)
        try:
            content = response["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise HttpProviderError("Ollama 响应缺少 message.content") from exc
        return self._parse_plan_text(content)

    def list_models(self) -> tuple[str, ...]:
        response = self._client.request("GET", self._base_url + "/v1/models")
        items = response.get("data")
        if not isinstance(items, list):
            raise HttpProviderError("Ollama 模型列表格式无效")
        return tuple(
            item["id"] for item in items
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        )

    def _check_ready(self, cancel_event: Event | None) -> None:
        self._check_cancelled(cancel_event)
        if not self.config.model:
            raise HttpProviderError("未配置本地模型名")

    @staticmethod
    def _validate_base_url(value: str) -> str:
        url = value.strip().rstrip("/")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HttpProviderError("本地模型服务地址必须是 HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HttpProviderError("本地模型服务地址不能包含凭据、查询或片段")
        return url

    @staticmethod
    def _check_cancelled(cancel_event: Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise ProviderCancelledError("请求已取消")

    @staticmethod
    def _parse_plan_text(content: Any) -> Mapping[str, Any]:
        if not isinstance(content, str):
            raise HttpProviderError("模型输出必须是 JSON 字符串")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HttpProviderError("模型输出不是有效的计划 JSON") from exc
        if not isinstance(parsed, Mapping):
            raise HttpProviderError("模型计划必须是 JSON 对象")
        return parsed


class OpenAIResponsesProvider(ModelProvider):
    def __init__(self, config: HttpProviderConfig):
        self.config = config
        self._endpoint = self._validate_endpoint(config.endpoint)
        self._client = HttpJsonClient(
            config.timeout_seconds, config.max_response_chars
        )

    @property
    def provider_id(self) -> str:
        return "openai_responses"

    def generate_plan(
        self, request: PlannerRequest, cancel_event: Event | None = None
    ) -> Mapping[str, Any]:
        OllamaProvider._check_cancelled(cancel_event)
        if not self.config.model:
            raise HttpProviderError("未配置远程模型名")
        if not self.config.api_key:
            raise HttpProviderError("未提供远程模型密钥")
        if any(ord(char) < 32 or ord(char) == 127 for char in self.config.api_key):
            raise HttpProviderError("远程模型密钥包含非法控制字符")
        response = self._client.request(
            "POST",
            self._endpoint,
            {
                "model": self.config.model,
                "instructions": SYSTEM_INSTRUCTIONS,
                "input": build_user_input(request),
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "gitora_commit_plan",
                        "strict": True,
                        "schema": build_plan_schema(request),
                    }
                },
            },
            {"Authorization": f"Bearer {self.config.api_key}"},
        )
        OllamaProvider._check_cancelled(cancel_event)
        return OllamaProvider._parse_plan_text(self._extract_output_text(response))

    @staticmethod
    def _validate_endpoint(value: str) -> str:
        url = value.strip()
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise HttpProviderError("远程 Responses API 必须使用完整 HTTPS URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise HttpProviderError("远程 API 地址不能包含凭据或片段")
        return url

    @staticmethod
    def _extract_output_text(response: Mapping[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str):
            return direct
        output = response.get("output")
        if isinstance(output, list):
            texts = []
            for item in output:
                if not isinstance(item, Mapping):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if (
                        isinstance(part, Mapping)
                        and part.get("type") == "output_text"
                        and isinstance(part.get("text"), str)
                    ):
                        texts.append(part["text"])
            if texts:
                return "".join(texts)
        raise HttpProviderError("Responses API 响应缺少输出文本")
