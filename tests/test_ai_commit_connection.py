# coding: utf-8
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.common.ai_commit_connection import (
    AiCommitCredentialService,
    create_model_provider,
)
from app.common.ai_commit_credentials import CredentialStoreError
from app.common.ai_commit_anthropic import AnthropicMessagesProvider
from app.common.ai_commit_http import (
    HttpProviderError,
    OllamaProvider,
    OpenAIChatProvider,
    OpenAIResponsesProvider,
)
from app.common.ai_commit_settings import AiCommitSettings, AiCommitSettingsStore


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"
ENV_NAME = "GITORA_CONNECTION_TEST_KEY"


class _MemoryCredentialStore:
    def __init__(self):
        self.values: dict[str, str] = {}

    def get(self, account: str) -> str:
        return self.values.get(account, "")

    def set(self, account: str, secret: str) -> None:
        self.values[account] = secret

    def delete(self, account: str) -> bool:
        return self.values.pop(account, None) is not None

    def has(self, account: str) -> bool:
        return bool(self.get(account))


class _UnavailableCredentialStore(_MemoryCredentialStore):
    def get(self, _account: str) -> str:
        raise CredentialStoreError("系统凭据库读取失败")


class AiCommitConnectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        config = Path(self.temp_dir.name) / "ai_commit.json"
        self.defaults = AiCommitSettingsStore(DEFAULTS, config).load()

    def remote_settings(
        self, endpoint: str = "https://example.invalid/v1/responses"
    ) -> AiCommitSettings:
        return self.defaults.with_user_values({
            "provider": "openai_responses",
            "remote_endpoint": endpoint,
            "remote_model": "remote-model",
            "api_key_env": ENV_NAME,
        })

    def test_factory_builds_local_and_remote_providers(self) -> None:
        local_settings = self.defaults.with_user_values({
            "local_endpoint": "http://127.0.0.1:11434",
            "local_model": "local-model",
        })
        local = create_model_provider(local_settings, "ignored-secret")
        remote = create_model_provider(self.remote_settings(), "remote-secret")

        self.assertIsInstance(local, OllamaProvider)
        self.assertEqual(local.config.api_key, "")
        self.assertIsInstance(remote, OpenAIResponsesProvider)
        self.assertEqual(remote.config.api_key, "remote-secret")

    def test_factory_uses_chat_for_remote_base_or_chat_endpoint(self) -> None:
        for endpoint in (
            "https://api.deepseek.com",
            "https://example.invalid/v1",
            "https://example.invalid/v1/chat/completions",
        ):
            with self.subTest(endpoint=endpoint):
                provider = create_model_provider(
                    self.remote_settings(endpoint), "remote-secret"
                )
                self.assertIsInstance(provider, OpenAIChatProvider)
                self.assertEqual(provider.config.api_key, "remote-secret")

    def test_factory_builds_anthropic_messages_provider(self) -> None:
        settings = self.remote_settings("https://api.anthropic.com").with_user_values({
            "provider": "anthropic",
            "remote_model": "claude-sonnet-4-20250514",
        })

        provider = create_model_provider(settings, "anthropic-secret")

        self.assertIsInstance(provider, AnthropicMessagesProvider)
        self.assertEqual(provider.config.api_key, "anthropic-secret")

    def test_system_key_precedes_environment_and_is_endpoint_scoped(self) -> None:
        service = AiCommitCredentialService(
            self.defaults.credential_service, _MemoryCredentialStore()
        )
        settings = self.remote_settings()
        other = self.remote_settings("https://other.invalid/v1/responses")

        with patch.dict(os.environ, {ENV_NAME: "environment-key"}):
            self.assertEqual(service.resolve_api_key(settings), "environment-key")
            self.assertTrue(service.store_api_key(settings, "system-key")[0])
            self.assertEqual(service.resolve_api_key(settings), "system-key")
            self.assertEqual(service.resolve_api_key(other), "environment-key")

    def test_anthropic_system_key_is_endpoint_scoped(self) -> None:
        service = AiCommitCredentialService(
            self.defaults.credential_service, _MemoryCredentialStore()
        )
        settings = self.remote_settings("https://api.anthropic.com").with_user_values({
            "provider": "anthropic",
        })

        self.assertTrue(service.store_api_key(settings, "anthropic-key")[0])
        self.assertEqual(service.resolve_api_key(settings), "anthropic-key")

    def test_failed_store_uses_environment_without_exposing_secret(self) -> None:
        service = AiCommitCredentialService(
            self.defaults.credential_service, _UnavailableCredentialStore()
        )
        settings = self.remote_settings()
        service.refresh(settings)

        self.assertFalse(service.available)
        with patch.dict(os.environ, {ENV_NAME: "fallback-secret"}):
            self.assertEqual(service.resolve_api_key(settings), "fallback-secret")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HttpProviderError) as captured:
                service.resolve_api_key(settings)
        self.assertNotIn("fallback-secret", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
