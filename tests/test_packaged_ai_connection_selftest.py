# coding: utf-8
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from tools.packaged_ai_connection_selftest import (
    CONNECTION_MARKER,
    CREDENTIAL_MARKER,
    MODEL_NAME,
    QML_MARKER,
    SPLASH_MARKER,
    SETTINGS_MARKER,
    PackagedSelftestError,
    _build_environment,
    run_connection_selftest,
)


class _StickyDeleteCredentialStore:
    def __init__(self):
        self.value = ""
        self.delete_calls = 0

    def set(self, _account: str, secret: str) -> None:
        self.value = secret

    def get(self, _account: str) -> str:
        return self.value

    def delete(self, _account: str) -> bool:
        self.delete_calls += 1
        if self.delete_calls >= 2:
            self.value = ""
        return True


class PackagedAiConnectionSelftestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.captured = {}

    def _connected_runner(self, args, **kwargs):
        environment = kwargs["env"]
        root = Path(environment["LOCALAPPDATA"])
        settings_path = (
            root / "Gitora" / "ai_commit.json"
            if os.name == "nt"
            else root / ".config" / "Gitora" / "ai_commit.json"
        )
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        with urllib.request.urlopen(
            settings["local_endpoint"] + "/v1/models", timeout=2
        ) as response:
            models = json.loads(response.read().decode("utf-8"))
        self.captured.update(
            args=args,
            cwd=kwargs["cwd"],
            settings=settings,
            environment=environment,
            models=models,
        )
        return subprocess.CompletedProcess(
            args,
            0,
            f"[SELFTEST] QML 加载成功,{QML_MARKER} 1\n"
            f"[SELFTEST] {SPLASH_MARKER}: 启动页已关闭\n"
            f"[SELFTEST] {SETTINGS_MARKER}: SettingsView 已加载\n"
            f"[SELFTEST] {CONNECTION_MARKER}: 检测到 1 个本地模型\n"
            f"[SELFTEST] {CREDENTIAL_MARKER}: "
            "原生系统凭据写入、读取和删除均通过\n",
            "",
        )

    def test_uses_isolated_settings_and_live_loopback_stub(self) -> None:

        output = run_connection_selftest(
            Path(sys.executable), timeout_seconds=5, runner=self._connected_runner
        )

        self.assertIn(CONNECTION_MARKER, output)
        self.assertEqual(self.captured["settings"]["local_model"], MODEL_NAME)
        self.assertNotIn("api_key", self.captured["settings"])
        self.assertEqual(self.captured["models"]["data"][0]["id"], MODEL_NAME)
        self.assertEqual(self.captured["environment"]["GITESS_QML_SELFTEST"], "1")
        self.assertEqual(
            self.captured["environment"]["GITESS_AI_CONNECTION_SELFTEST"], "1"
        )
        self.assertEqual(
            self.captured["environment"]["GITESS_SETTINGS_NAV_SELFTEST"], "1"
        )
        self.assertEqual(
            self.captured["environment"]["GITESS_CREDENTIAL_SELFTEST"], "1"
        )
        self.assertEqual(self.captured["environment"]["PYTHONUTF8"], "1")
        self.assertEqual(
            self.captured["environment"]["PYTHONIOENCODING"], "utf-8"
        )
        self.assertEqual(self.captured["environment"]["PYTHONUNBUFFERED"], "1")

    def test_resolves_relative_executable_before_changing_cwd(self) -> None:
        relative_executable = Path(os.path.relpath(sys.executable, Path.cwd()))

        run_connection_selftest(
            relative_executable,
            timeout_seconds=5,
            runner=self._connected_runner,
        )

        resolved_executable = Path(sys.executable).resolve()
        self.assertEqual(Path(self.captured["args"][0]), resolved_executable)
        self.assertEqual(Path(self.captured["cwd"]), resolved_executable.parent)

    def test_macos_keeps_user_home_and_isolates_xdg_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(
            os.environ, {"HOME": "/Users/gitora-selftest"}, clear=False
        ), patch(
            "tools.packaged_ai_connection_selftest.sys.platform", "darwin"
        ):
            root = Path(temp)
            environment = _build_environment(root, "http://127.0.0.1:11434")

        self.assertEqual(environment["HOME"], "/Users/gitora-selftest")
        self.assertEqual(
            environment["XDG_CONFIG_HOME"], str(root / ".config")
        )

    def test_credential_selftest_retries_cleanup_after_false_delete_success(self) -> None:
        from app_qml import main_qml

        store = _StickyDeleteCredentialStore()
        with patch.object(
            main_qml,
            "_create_credential_selftest_context",
            return_value=(store, "packaged-selftest", "temporary-secret"),
        ):
            ok, message = main_qml._run_system_credential_selftest()

        self.assertFalse(ok)
        self.assertIn("仍可读取", message)
        self.assertEqual(store.delete_calls, 2)
        self.assertEqual(store.value, "")

    def test_rejects_success_marker_without_loopback_request(self) -> None:
        def disconnected_runner(args, **_kwargs):
            return subprocess.CompletedProcess(
                args, 0, f"{QML_MARKER}\n{CONNECTION_MARKER}", ""
            )

        with self.assertRaisesRegex(PackagedSelftestError, "未访问回环"):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5, runner=disconnected_runner
            )

    def test_timeout_preserves_partial_process_output(self) -> None:
        def timed_out_runner(args, **_kwargs):
            raise subprocess.TimeoutExpired(
                args,
                5,
                output=b"[SELFTEST] QML loaded before timeout\n",
                stderr=b"credential check pending\n",
            )

        with self.assertRaisesRegex(
            PackagedSelftestError, "QML loaded before timeout"
        ) as raised:
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5, runner=timed_out_runner
            )
        self.assertIn("credential check pending", str(raised.exception))

    def test_rejects_successful_process_without_connection_marker(self) -> None:
        with self.assertRaisesRegex(PackagedSelftestError, CONNECTION_MARKER):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5,
                runner=self._connected_runner_without_marker,
            )

    def test_rejects_successful_process_without_splash_marker(self) -> None:
        with self.assertRaisesRegex(PackagedSelftestError, SPLASH_MARKER):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5,
                runner=self._connected_runner_without_splash_marker,
            )

    def test_rejects_successful_process_without_settings_marker(self) -> None:
        with self.assertRaisesRegex(PackagedSelftestError, SETTINGS_MARKER):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5,
                runner=self._connected_runner_without_settings_marker,
            )

    def test_rejects_successful_process_without_credential_marker(self) -> None:
        with self.assertRaisesRegex(PackagedSelftestError, CREDENTIAL_MARKER):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5,
                runner=self._connected_runner_without_credential_marker,
            )

    def _connected_runner_without_marker(self, args, **kwargs):
        completed = self._connected_runner(args, **kwargs)
        completed.stdout = QML_MARKER
        return completed

    def _connected_runner_without_splash_marker(self, args, **kwargs):
        completed = self._connected_runner(args, **kwargs)
        completed.stdout = completed.stdout.replace(SPLASH_MARKER, "")
        return completed

    def _connected_runner_without_settings_marker(self, args, **kwargs):
        completed = self._connected_runner(args, **kwargs)
        completed.stdout = f"{QML_MARKER}\n{CONNECTION_MARKER}"
        return completed

    def _connected_runner_without_credential_marker(self, args, **kwargs):
        completed = self._connected_runner(args, **kwargs)
        completed.stdout = completed.stdout.replace(CREDENTIAL_MARKER, "")
        return completed


if __name__ == "__main__":
    unittest.main()
