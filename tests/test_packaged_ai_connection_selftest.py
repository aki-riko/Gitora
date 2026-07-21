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
    def test_uses_isolated_settings_and_live_loopback_stub(self) -> None:
        captured = {}

        def fake_runner(args, **kwargs):
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
            captured.update(settings=settings, environment=environment, models=models)
            return subprocess.CompletedProcess(
                args, 0,
                f"[SELFTEST] QML 加载成功,{QML_MARKER} 1\n"
                f"[SELFTEST] {CONNECTION_MARKER}: 检测到 1 个本地模型\n",
                "",
            )

        output = run_connection_selftest(
            Path(sys.executable), timeout_seconds=5, runner=fake_runner
        )

        self.assertIn(CONNECTION_MARKER, output)
        self.assertEqual(captured["settings"]["local_model"], MODEL_NAME)
        self.assertNotIn("api_key", captured["settings"])
        self.assertEqual(captured["models"]["data"][0]["id"], MODEL_NAME)
        self.assertEqual(captured["environment"]["GITESS_QML_SELFTEST"], "1")
        self.assertEqual(
            captured["environment"]["GITESS_AI_CONNECTION_SELFTEST"], "1"
        )

    def test_rejects_successful_process_without_connection_marker(self) -> None:
        def fake_runner(args, **_kwargs):
            return subprocess.CompletedProcess(args, 0, QML_MARKER, "")

        with self.assertRaisesRegex(PackagedSelftestError, CONNECTION_MARKER):
            run_connection_selftest(
                Path(sys.executable), timeout_seconds=5, runner=fake_runner
            )


if __name__ == "__main__":
    unittest.main()
