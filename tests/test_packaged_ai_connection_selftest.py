# coding: utf-8
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
import urllib.request
from pathlib import Path

from tools.packaged_ai_connection_selftest import (
    CONNECTION_MARKER,
    MODEL_NAME,
    QML_MARKER,
    PackagedSelftestError,
    run_connection_selftest,
)


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
            settings=settings, environment=environment, models=models
        )
        return subprocess.CompletedProcess(
            args, 0,
            f"[SELFTEST] QML 加载成功,{QML_MARKER} 1\n"
            f"[SELFTEST] {CONNECTION_MARKER}: 检测到 1 个本地模型\n",
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
        self.assertEqual(self.captured["environment"]["PYTHONUTF8"], "1")
        self.assertEqual(
            self.captured["environment"]["PYTHONIOENCODING"], "utf-8"
        )

    def test_rejects_success_marker_without_loopback_request(self) -> None:
        def disconnected_runner(args, **_kwargs):
            return subprocess.CompletedProcess(
                args, 0, f"{QML_MARKER}\n{CONNECTION_MARKER}", ""
            )

        with self.assertRaisesRegex(PackagedSelftestError, "未访问回环"):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5, runner=disconnected_runner
            )

    def test_rejects_successful_process_without_connection_marker(self) -> None:
        with self.assertRaisesRegex(PackagedSelftestError, CONNECTION_MARKER):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5,
                runner=self._connected_runner_without_marker,
            )

    def _connected_runner_without_marker(self, args, **kwargs):
        completed = self._connected_runner(args, **kwargs)
        completed.stdout = QML_MARKER
        return completed


if __name__ == "__main__":
    unittest.main()
