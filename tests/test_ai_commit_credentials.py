# coding: utf-8
from __future__ import annotations

import sys
import unittest
import uuid

from app.common.ai_commit_credentials import (
    CredentialStoreError,
    SystemCredentialStore,
    create_native_backend,
    credential_account,
)


class _MemoryBackend:
    def __init__(self):
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.values[(service, username)]


class _FailingBackend(_MemoryBackend):
    def get_password(self, service: str, username: str) -> str | None:
        raise RuntimeError("backend-secret-detail")


class AiCommitCredentialsTest(unittest.TestCase):
    def test_account_is_stable_isolated_and_hides_endpoint(self) -> None:
        endpoint = "https://api.example.invalid/v1/responses"
        account = credential_account("openai_responses", endpoint)

        self.assertEqual(account, credential_account("openai_responses", endpoint))
        self.assertNotIn(endpoint, account)
        self.assertNotEqual(
            account,
            credential_account("openai_responses", endpoint + "/other"),
        )

    def test_account_requires_provider_and_endpoint(self) -> None:
        with self.assertRaisesRegex(CredentialStoreError, "提供方"):
            credential_account("", "https://example.invalid")
        with self.assertRaisesRegex(CredentialStoreError, "远程端点"):
            credential_account("openai_responses", "")

    def test_store_round_trip_and_delete(self) -> None:
        backend = _MemoryBackend()
        store = SystemCredentialStore("Gitora.Test", backend)

        self.assertFalse(store.has("account"))
        store.set("account", "top-secret")
        self.assertTrue(store.has("account"))
        self.assertEqual(store.get("account"), "top-secret")
        self.assertTrue(store.delete("account"))
        self.assertFalse(store.delete("account"))

    def test_secret_validation_and_backend_errors_are_sanitized(self) -> None:
        store = SystemCredentialStore("Gitora.Test", _MemoryBackend())
        with self.assertRaisesRegex(CredentialStoreError, "账户"):
            store.get("")
        with self.assertRaisesRegex(CredentialStoreError, "不能为空"):
            store.set("account", "")
        with self.assertRaisesRegex(CredentialStoreError, "控制字符"):
            store.set("account", "bad\nsecret")

        failing = SystemCredentialStore("Gitora.Test", _FailingBackend())
        with self.assertRaises(CredentialStoreError) as captured:
            failing.get("account")
        self.assertNotIn("backend-secret-detail", str(captured.exception))

    def test_unsupported_platform_is_rejected_without_fallback(self) -> None:
        with self.assertRaisesRegex(CredentialStoreError, "不支持"):
            create_native_backend("linux")

    @unittest.skipUnless(sys.platform == "win32", "仅 Windows 验证持久级别")
    def test_windows_backend_persists_beyond_logon_session(self) -> None:
        from keyring.backends.Windows import win32cred

        backend = create_native_backend()

        self.assertEqual(
            backend.persist,
            win32cred.CRED_PERSIST_LOCAL_MACHINE,
        )
        self.assertNotEqual(backend.persist, win32cred.CRED_PERSIST_SESSION)

    @unittest.skipUnless(
        sys.platform in {"win32", "darwin"},
        "真实系统凭据库测试仅在 Windows/macOS 运行",
    )
    def test_native_system_store_round_trip(self) -> None:
        service = f"Gitora.AiCommit.Test.{uuid.uuid4()}"
        account = "native-round-trip"
        secret = f"test-secret-{uuid.uuid4()}"
        store = SystemCredentialStore(service)
        self.addCleanup(lambda: store.delete(account) if store.has(account) else None)
        self.assertFalse(store.has(account))
        store.set(account, secret)
        self.assertEqual(store.get(account), secret)
        self.assertTrue(store.delete(account))
        self.assertFalse(store.has(account))


if __name__ == "__main__":
    unittest.main()
