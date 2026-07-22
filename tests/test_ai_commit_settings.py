# coding: utf-8
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.common.ai_commit_settings import (
    AiCommitSettingsError,
    AiCommitSettingsStore,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class AiCommitSettingsTest(unittest.TestCase):
    def test_repository_defaults_are_complete_and_safe(self) -> None:
        settings = AiCommitSettingsStore(
            defaults_path=DEFAULTS,
            config_path=Path("missing-user-config.json"),
        ).load()
        self.assertFalse(settings.enabled)
        self.assertEqual(settings.provider, "ollama")
        self.assertEqual(settings.local_endpoint, "")
        self.assertEqual(settings.remote_endpoint, "")
        self.assertEqual(settings.credential_service, "Gitora.AiCommit")
        self.assertGreater(settings.limits.max_total_chars, 0)

    def test_user_settings_round_trip_without_secret_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "ai_commit.json"
            store = AiCommitSettingsStore(DEFAULTS, config)
            changed = store.load().with_user_values({
                "enabled": True,
                "provider": "openai_responses",
                "remote_endpoint": "https://example.invalid/v1/responses",
                "remote_model": "configured-model",
                "api_key_env": "GITORA_TEST_KEY",
            })
            store.save(changed)
            reloaded = store.load()

            self.assertEqual(reloaded, changed)
            payload = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(payload["credential_service"], "Gitora.AiCommit")
            self.assertNotIn("api_key", payload)
            self.assertNotIn("secret", json.dumps(payload).lower())

    def test_invalid_provider_scope_and_environment_name_are_rejected(self) -> None:
        settings = AiCommitSettingsStore(DEFAULTS, Path("missing.json")).load()
        with self.assertRaisesRegex(AiCommitSettingsError, "提供方"):
            settings.with_user_values({"provider": "unknown"})
        with self.assertRaisesRegex(AiCommitSettingsError, "发送范围"):
            settings.with_user_values({"remote_scope": "everything"})
        with self.assertRaisesRegex(AiCommitSettingsError, "环境变量"):
            settings.with_user_values({"api_key_env": "BAD-NAME"})
        with self.assertRaisesRegex(AiCommitSettingsError, "环境变量"):
            settings.with_user_values({"api_key_env": "1BAD"})
        with self.assertRaisesRegex(AiCommitSettingsError, "环境变量"):
            settings.with_user_values({"api_key_env": "密钥"})

    def test_unknown_user_setting_is_rejected(self) -> None:
        settings = AiCommitSettingsStore(DEFAULTS, Path("missing.json")).load()
        with self.assertRaisesRegex(AiCommitSettingsError, "不支持"):
            settings.with_user_values({"api_key": "must-not-persist"})


if __name__ == "__main__":
    unittest.main()
