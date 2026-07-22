# coding: utf-8
"""AI 提交规划器的 Windows/macOS 原生系统凭据库。"""
from __future__ import annotations

import hashlib
import sys
from threading import RLock
from typing import NoReturn, Protocol

from .logger import get_logger


logger = get_logger("AiCommitCredentials")


class CredentialStoreError(RuntimeError):
    """系统凭据库不可用或拒绝操作。"""


class CredentialStore(Protocol):
    def get(self, account: str) -> str: ...

    def set(self, account: str, secret: str) -> None: ...

    def delete(self, account: str) -> bool: ...

    def has(self, account: str) -> bool: ...


class _NativeBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def credential_account(provider: str, endpoint: str) -> str:
    """按提供方和精确端点隔离凭据，同时不向系统库暴露完整端点。"""
    normalized_provider = provider.strip()
    normalized_endpoint = endpoint.strip()
    if not normalized_provider or not normalized_endpoint:
        raise CredentialStoreError("保存密钥前必须配置提供方和远程端点")
    identity = f"{normalized_provider}\0{normalized_endpoint}".encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    return f"{normalized_provider}:{digest}"


def create_native_backend(platform: str | None = None) -> _NativeBackend:
    """只实例化操作系统原生后端，禁止自动选择其他 keyring。"""
    current = platform or sys.platform
    try:
        if current == "win32":
            from keyring.backends.Windows import WinVaultKeyring

            backend = WinVaultKeyring()
            backend.persist = "local machine"
            return backend
        if current == "darwin":
            from keyring.backends.macOS import Keyring

            return Keyring()
    except Exception as exc:
        logger.warning(f"初始化系统凭据库失败: {type(exc).__name__}")
        raise CredentialStoreError("无法初始化系统凭据库") from exc
    raise CredentialStoreError("当前系统不支持 Gitora 系统凭据库")


class SystemCredentialStore:
    """不缓存密钥，只在需要时读写当前用户的原生凭据库。"""

    def __init__(
        self,
        service: str,
        backend: _NativeBackend | None = None,
    ):
        self._service = service.strip()
        if not self._service:
            raise CredentialStoreError("系统凭据服务名不能为空")
        self._backend = backend or create_native_backend()
        self._lock = RLock()

    def get(self, account: str) -> str:
        self._validate_account(account)
        with self._lock:
            return self._get_unlocked(account)

    def _get_unlocked(self, account: str) -> str:
        try:
            value = self._backend.get_password(self._service, account)
        except Exception as exc:
            self._raise_operation_error("读取", exc)
        if value is None:
            return ""
        if not isinstance(value, str):
            raise CredentialStoreError("系统凭据库返回了无效密钥")
        return value

    def set(self, account: str, secret: str) -> None:
        if not account:
            raise CredentialStoreError("系统凭据账户不能为空")
        if not secret:
            raise CredentialStoreError("密钥不能为空")
        if any(ord(char) < 32 or ord(char) == 127 for char in secret):
            raise CredentialStoreError("密钥包含非法控制字符")
        with self._lock:
            try:
                self._backend.set_password(self._service, account, secret)
            except Exception as exc:
                self._raise_operation_error("保存", exc)

    def delete(self, account: str) -> bool:
        self._validate_account(account)
        with self._lock:
            if not self._get_unlocked(account):
                return False
            try:
                self._backend.delete_password(self._service, account)
            except Exception as exc:
                self._raise_operation_error("删除", exc)
            return True

    def has(self, account: str) -> bool:
        return bool(self.get(account))

    @staticmethod
    def _validate_account(account: str) -> None:
        if not account:
            raise CredentialStoreError("系统凭据账户不能为空")

    @staticmethod
    def _raise_operation_error(operation: str, exc: Exception) -> NoReturn:
        logger.warning(f"{operation}系统凭据失败: {type(exc).__name__}")
        raise CredentialStoreError(f"系统凭据库{operation}失败") from exc
