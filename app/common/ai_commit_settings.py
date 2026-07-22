# coding: utf-8
"""AI 提交规划器的非敏感配置存储。"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from .ai_commit_context import SnapshotLimits
from .setting import CONFIG_FOLDER


PROVIDERS = {"ollama", "openai_responses"}
REMOTE_SCOPES = {"staged", "all"}


class AiCommitSettingsError(ValueError):
    """配置缺失、损坏或包含不支持的值。"""


@dataclass(frozen=True)
class AiCommitSettings:
    enabled: bool
    provider: str
    local_endpoint: str
    local_model: str
    remote_endpoint: str
    remote_model: str
    api_key_env: str
    credential_service: str
    generate_body: bool
    remote_scope: str
    limits: SnapshotLimits
    timeout_seconds: int
    max_response_chars: int

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AiCommitSettings":
        try:
            limits = data["limits"]
            network = data["network"]
            settings = cls(
                enabled=cls._bool(data, "enabled"),
                provider=cls._string(data, "provider"),
                local_endpoint=cls._string(data, "local_endpoint"),
                local_model=cls._string(data, "local_model"),
                remote_endpoint=cls._string(data, "remote_endpoint"),
                remote_model=cls._string(data, "remote_model"),
                api_key_env=cls._string(data, "api_key_env"),
                credential_service=cls._string(data, "credential_service"),
                generate_body=cls._bool(data, "generate_body"),
                remote_scope=cls._string(data, "remote_scope"),
                limits=SnapshotLimits(
                    max_total_chars=cls._positive_int(limits, "max_total_chars"),
                    max_file_chars=cls._positive_int(limits, "max_file_chars"),
                    max_untracked_chars=cls._positive_int(limits, "max_untracked_chars"),
                    max_instruction_chars=cls._positive_int(limits, "max_instruction_chars"),
                    max_files=cls._positive_int(limits, "max_files"),
                    history_count=cls._positive_int(limits, "history_count"),
                    instruction_files=tuple(cls._string_list(limits, "instruction_files")),
                ),
                timeout_seconds=cls._positive_int(network, "timeout_seconds"),
                max_response_chars=cls._positive_int(network, "max_response_chars"),
            )
        except (KeyError, TypeError) as exc:
            raise AiCommitSettingsError(f"AI 配置缺少字段: {exc}") from exc
        if settings.provider not in PROVIDERS:
            raise AiCommitSettingsError("不支持的模型提供方")
        if settings.remote_scope not in REMOTE_SCOPES:
            raise AiCommitSettingsError("不支持的远程发送范围")
        if settings.api_key_env and not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", settings.api_key_env
        ):
            raise AiCommitSettingsError("密钥环境变量名不合法")
        if not settings.credential_service:
            raise AiCommitSettingsError("系统凭据服务名不能为空")
        return settings

    def to_mapping(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "local_endpoint": self.local_endpoint,
            "local_model": self.local_model,
            "remote_endpoint": self.remote_endpoint,
            "remote_model": self.remote_model,
            "api_key_env": self.api_key_env,
            "credential_service": self.credential_service,
            "generate_body": self.generate_body,
            "remote_scope": self.remote_scope,
            "limits": asdict(self.limits),
            "network": {
                "timeout_seconds": self.timeout_seconds,
                "max_response_chars": self.max_response_chars,
            },
        }

    def with_user_values(self, values: Mapping[str, Any]) -> "AiCommitSettings":
        allowed = {
            "enabled", "provider", "local_endpoint", "local_model",
            "remote_endpoint", "remote_model", "api_key_env",
            "generate_body", "remote_scope",
        }
        unknown = set(values) - allowed
        if unknown:
            raise AiCommitSettingsError("包含不支持的设置字段")
        merged = self.to_mapping()
        merged.update(values)
        return self.from_mapping(merged)

    @staticmethod
    def _string(data: Mapping[str, Any], key: str) -> str:
        value = data[key]
        if not isinstance(value, str):
            raise AiCommitSettingsError(f"{key} 必须是字符串")
        return value.strip()

    @staticmethod
    def _bool(data: Mapping[str, Any], key: str) -> bool:
        value = data[key]
        if not isinstance(value, bool):
            raise AiCommitSettingsError(f"{key} 必须是布尔值")
        return value

    @staticmethod
    def _positive_int(data: Mapping[str, Any], key: str) -> int:
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise AiCommitSettingsError(f"{key} 必须是正整数")
        return value

    @staticmethod
    def _string_list(data: Mapping[str, Any], key: str) -> list[str]:
        value = data[key]
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(item, str) for item in value
        ):
            raise AiCommitSettingsError(f"{key} 必须是字符串数组")
        return list(value)


class AiCommitSettingsStore:
    """合并只读默认配置和用户覆盖；敏感密钥不属于本存储。"""

    def __init__(
        self,
        defaults_path: Path | None = None,
        config_path: Path | None = None,
    ):
        self.defaults_path = defaults_path or self._resolve_defaults_path()
        self.config_path = config_path or (CONFIG_FOLDER / "ai_commit.json")

    def load(self) -> AiCommitSettings:
        defaults = self._read_json(self.defaults_path, required=True)
        user = self._read_json(self.config_path, required=False)
        merged = self._deep_merge(defaults, user)
        return AiCommitSettings.from_mapping(merged)

    def save(self, settings: AiCommitSettings) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.config_path.with_suffix(self.config_path.suffix + ".tmp")
        payload = json.dumps(
            settings.to_mapping(), ensure_ascii=False, indent=2, sort_keys=True
        ) + "\n"
        temp_path.write_text(payload, encoding="utf-8")
        os.replace(temp_path, self.config_path)

    @staticmethod
    def _read_json(path: Path, required: bool) -> dict[str, Any]:
        if not path.is_file():
            if required:
                raise AiCommitSettingsError(f"缺少默认配置文件: {path.name}")
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AiCommitSettingsError(f"无法读取配置文件 {path.name}") from exc
        if not isinstance(data, dict):
            raise AiCommitSettingsError(f"配置文件 {path.name} 必须是对象")
        return data

    @classmethod
    def _deep_merge(
        cls, base: Mapping[str, Any], override: Mapping[str, Any]
    ) -> dict[str, Any]:
        result = dict(base)
        for key, value in override.items():
            if isinstance(result.get(key), Mapping) and isinstance(value, Mapping):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _resolve_defaults_path() -> Path:
        relative = Path("app") / "resource" / "config" / "ai_commit_defaults.json"
        module_root = Path(__file__).resolve().parents[2]
        executable = Path(sys.executable).resolve().parent
        candidates = (
            module_root / relative,
            executable / relative,
            executable.parent / "Resources" / relative,
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]
