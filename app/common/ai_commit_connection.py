# coding: utf-8
"""AI 提交规划器的提供方创建与系统凭据访问。"""
from __future__ import annotations

import os
from typing import Callable

from .ai_commit_credentials import (
    CredentialStore,
    CredentialStoreError,
    SystemCredentialStore,
    credential_account,
)
from .ai_commit_http import (
    HttpProviderConfig,
    HttpProviderError,
    OllamaProvider,
    OpenAIResponsesProvider,
)
from .ai_commit_provider import ModelProvider
from .ai_commit_settings import AiCommitSettings, AiCommitSettingsError
from .logger import get_logger


logger = get_logger("AiCommitConnection")
ProviderFactory = Callable[[AiCommitSettings, str], ModelProvider]


def create_model_provider(
    settings: AiCommitSettings, api_key: str
) -> ModelProvider:
    """根据不可变设置快照创建对应模型提供方。"""
    if settings.provider == "ollama":
        config = HttpProviderConfig(
            settings.local_endpoint, settings.local_model, "",
            settings.timeout_seconds, settings.max_response_chars,
        )
        return OllamaProvider(config)
    if settings.provider == "openai_responses":
        config = HttpProviderConfig(
            settings.remote_endpoint, settings.remote_model, api_key,
            settings.timeout_seconds, settings.max_response_chars,
        )
        return OpenAIResponsesProvider(config)
    raise AiCommitSettingsError("不支持的模型提供方")


class AiCommitCredentialService:
    """管理系统凭据状态与环境变量回退，不向界面暴露密钥。"""

    def __init__(
        self,
        credential_service: str,
        provided_store: CredentialStore | None = None,
    ):
        self._store, self._error = self._initialize_store(
            credential_service, provided_store
        )
        self._has_stored_api_key = False

    @staticmethod
    def _initialize_store(
        credential_service: str,
        provided: CredentialStore | None,
    ) -> tuple[CredentialStore | None, str]:
        if provided is not None:
            return provided, ""
        try:
            return SystemCredentialStore(credential_service), ""
        except CredentialStoreError as exc:
            logger.warning(f"初始化 AI 系统凭据库失败: {type(exc).__name__}")
            return None, str(exc)

    @property
    def has_stored_api_key(self) -> bool:
        return self._has_stored_api_key

    @property
    def available(self) -> bool:
        return self._store is not None and not self._error

    @property
    def error(self) -> str:
        return self._error

    @staticmethod
    def has_environment_api_key(settings: AiCommitSettings) -> bool:
        return bool(settings.api_key_env and os.environ.get(settings.api_key_env))

    def store_api_key(
        self, settings: AiCommitSettings, value: str
    ) -> tuple[bool, str]:
        try:
            self._require_store().set(self._account(settings), value)
        except CredentialStoreError as exc:
            logger.warning(f"保存 AI 系统凭据失败: {type(exc).__name__}")
            self._error = str(exc)
            return False, str(exc)
        self._error = ""
        self._has_stored_api_key = True
        return True, "密钥已保存到系统凭据库"

    def delete_stored_api_key(
        self, settings: AiCommitSettings
    ) -> tuple[bool, str]:
        try:
            deleted = self._require_store().delete(self._account(settings))
        except CredentialStoreError as exc:
            logger.warning(f"删除 AI 系统凭据失败: {type(exc).__name__}")
            self._error = str(exc)
            return False, str(exc)
        self._error = ""
        self._has_stored_api_key = False
        message = "系统凭据已删除" if deleted else "当前端点没有已保存密钥"
        return True, message

    def resolve_api_key(self, settings: AiCommitSettings) -> str:
        if settings.provider != "openai_responses":
            return ""
        store_error = self._error
        if self._store is not None:
            try:
                secret = self._store.get(self._account(settings))
            except CredentialStoreError as exc:
                logger.warning(f"读取 AI 系统凭据失败: {type(exc).__name__}")
                store_error = str(exc)
            else:
                store_error = ""
                self._error = ""
                if secret:
                    return secret
        environment_secret = (
            os.environ.get(settings.api_key_env, "") if settings.api_key_env else ""
        )
        if environment_secret:
            return environment_secret
        if store_error:
            raise HttpProviderError(store_error)
        return ""

    def refresh(self, settings: AiCommitSettings) -> None:
        self._has_stored_api_key = False
        if (
            settings.provider != "openai_responses"
            or not settings.remote_endpoint
        ):
            return
        if self._store is None:
            if not self._error:
                self._error = "系统凭据库不可用"
            return
        try:
            self._has_stored_api_key = self._store.has(self._account(settings))
        except CredentialStoreError as exc:
            logger.warning(f"刷新 AI 系统凭据状态失败: {type(exc).__name__}")
            self._error = str(exc)
            return
        self._error = ""

    def _require_store(self) -> CredentialStore:
        if self._store is None:
            raise CredentialStoreError(self._error or "系统凭据库不可用")
        return self._store

    @staticmethod
    def _account(settings: AiCommitSettings) -> str:
        if settings.provider != "openai_responses":
            raise CredentialStoreError("系统凭据仅用于远程 Responses API")
        return credential_account(settings.provider, settings.remote_endpoint)
