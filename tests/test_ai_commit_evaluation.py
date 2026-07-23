# coding: utf-8
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.common.ai_commit_evaluation import (
    EvaluationError,
    EvaluationRunner,
    HistoryReplayBuilder,
    read_case_manifest,
    replay_workspace,
    write_case_manifest,
    write_manual_template,
)
from app.common.ai_commit_anthropic import AnthropicMessagesProvider
from app.common.ai_commit_provider import ModelProvider
from app.common.ai_commit_http import OpenAIChatProvider
from app.common.ai_commit_settings import AiCommitSettingsStore
from tests.git_test_utils import commit_all, init_repo, write_file
from tools import ai_commit_eval


ROOT = Path(__file__).resolve().parents[1]
DEFAULTS = ROOT / "app" / "resource" / "config" / "ai_commit_defaults.json"


class _CoveringProvider(ModelProvider):
    @property
    def provider_id(self) -> str:
        return "evaluation-test"

    def generate_plan(self, request, cancel_event=None):
        return {
            "schema_version": "1",
            "snapshot_id": request.snapshot.snapshot_id,
            "level": request.level,
            "summary": "历史回放计划",
            "groups": [{
                "group_id": "all",
                "title": "test: 历史回放",
                "body": "",
                "change_ids": list(request.snapshot.expected_ids(request.level)),
                "depends_on": [],
                "rationale": "覆盖全部改动",
                "warnings": [],
            }],
            "unassigned_change_ids": [],
            "warnings": [],
        }


class _FailingProvider(ModelProvider):
    @property
    def provider_id(self) -> str:
        return "failing-test"

    def generate_plan(self, request, cancel_event=None):
        raise RuntimeError("injected provider failure")


class _IncompleteProvider(_CoveringProvider):
    def generate_plan(self, request, cancel_event=None):
        result = super().generate_plan(request, cancel_event)
        result["groups"] = []
        result["unassigned_change_ids"] = list(
            request.snapshot.expected_ids(request.level)
        )
        return result


class AiCommitEvaluationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.repo = init_repo(root / "repo")
        paths = [
            "src/sample.py", "app/View.qml", "tests/test_sample.py",
            "docs/readme.md", "src/sample.py", "app/View.qml", "docs/readme.md",
        ]
        contents: dict[str, str] = {}
        for index, path in enumerate(paths, start=1):
            contents[path] = contents.get(path, "") + f"change {index}\n"
            write_file(self.repo, path, contents[path])
            commit_all(self.repo, f"test: history {index}")
        self.settings = AiCommitSettingsStore(
            DEFAULTS, root / "settings.json"
        ).load()
        self.cases = HistoryReplayBuilder(
            str(self.repo), self.settings.timeout_seconds
        ).build(3, 2)

    def test_builder_creates_non_overlapping_real_history_cases(self) -> None:
        self.assertEqual(len(self.cases), 3)
        targets = [commit for case in self.cases for commit in case.target_commits]
        self.assertEqual(len(targets), len(set(targets)))
        self.assertTrue(all(len(case.combined_diff_sha256) == 64 for case in self.cases))
        self.assertTrue(any("python" in case.categories for case in self.cases))
        self.assertTrue(any("qml" in case.categories for case in self.cases))
        self.assertTrue(all(not Path(path).is_absolute() for case in self.cases for path in case.changed_paths))

    def test_manifest_and_manual_template_keep_source_out_of_records(self) -> None:
        root = Path(self.temp_dir.name)
        manifest = root / "cases.jsonl"
        manual = root / "manual.csv"
        write_case_manifest(manifest, self.cases)
        write_manual_template(manual, self.cases)

        loaded = read_case_manifest(manifest)
        with manual.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(loaded, self.cases)
        self.assertEqual(len(rows), 6)
        self.assertEqual({row["status"] for row in rows}, {"not_run"})
        self.assertNotIn(str(self.repo), manifest.read_text(encoding="utf-8"))

    def test_replay_snapshot_and_hard_metrics_use_real_temporary_repo(self) -> None:
        case = self.cases[0]
        with replay_workspace(
            str(self.repo), case, self.settings.limits,
            self.settings.timeout_seconds,
        ) as replay:
            repo_path, _service, snapshot = replay
            self.assertNotEqual(Path(repo_path), self.repo)
            self.assertEqual(snapshot.head, case.base_commit)
            self.assertTrue(snapshot.changes)

        record = EvaluationRunner(
            str(self.repo), self.settings.limits, self.settings.timeout_seconds
        ).run_case(case, _CoveringProvider(), "local", "test-model")

        self.assertEqual(record.status, "passed")
        self.assertTrue(record.protocol_valid)
        self.assertEqual(record.coverage_percent, 100)
        self.assertEqual(record.duplicate_count, 0)
        self.assertTrue(record.patch_valid)
        self.assertGreaterEqual(record.total_latency_ms, record.provider_latency_ms)

    def test_provider_failure_records_type_without_fabricating_scores(self) -> None:
        record = EvaluationRunner(
            str(self.repo), self.settings.limits, self.settings.timeout_seconds
        ).run_case(self.cases[0], _FailingProvider(), "remote", "test-model")

        self.assertEqual(record.status, "failed")
        self.assertEqual(record.failure_type, "RuntimeError")
        self.assertFalse(record.protocol_valid)
        self.assertEqual(record.coverage_percent, 0)
        self.assertFalse(record.patch_valid)

    def test_incomplete_plan_records_hard_gate_failure(self) -> None:
        record = EvaluationRunner(
            str(self.repo), self.settings.limits, self.settings.timeout_seconds
        ).run_case(self.cases[0], _IncompleteProvider(), "local", "test-model")

        self.assertEqual(record.status, "failed")
        self.assertEqual(record.failure_type, "coverage")
        self.assertTrue(record.protocol_valid)
        self.assertEqual(record.coverage_percent, 0)

    def test_manifest_rejects_revision_option_injection(self) -> None:
        root = Path(self.temp_dir.name)
        manifest = root / "unsafe.jsonl"
        payload = self.cases[0].to_mapping()
        payload["base_commit"] = "--help"
        manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(EvaluationError, "提交哈希"):
            read_case_manifest(manifest)

    def test_source_upload_consent_covers_non_loopback_ollama(self) -> None:
        loopback = self.settings.with_user_values({
            "local_endpoint": "http://127.0.0.1:11434",
        })
        lan = self.settings.with_user_values({
            "local_endpoint": "http://192.168.1.20:11434",
        })

        self.assertFalse(
            ai_commit_eval.source_upload_requires_consent(loopback, "local")
        )
        self.assertTrue(
            ai_commit_eval.source_upload_requires_consent(lan, "local")
        )
        self.assertTrue(
            ai_commit_eval.source_upload_requires_consent(loopback, "remote")
        )

    def test_remote_evaluation_uses_same_chat_protocol_selection(self) -> None:
        settings = self.settings.with_user_values({
            "remote_endpoint": "https://api.deepseek.com",
            "remote_model": "deepseek-v4-pro",
            "api_key_env": "GITORA_EVALUATION_TEST_KEY",
        })

        with mock.patch.dict(
            "os.environ", {"GITORA_EVALUATION_TEST_KEY": "test-secret"}
        ):
            provider, model = ai_commit_eval.create_provider(settings, "remote")

        self.assertIsInstance(provider, OpenAIChatProvider)
        self.assertEqual(provider.config.api_key, "test-secret")
        self.assertEqual(model, "deepseek-v4-pro")

        anthropic_settings = settings.with_user_values({
            "provider": "anthropic",
            "remote_endpoint": "https://api.anthropic.com",
            "remote_model": "claude-sonnet-4-20250514",
        })
        with mock.patch.dict(
            "os.environ", {"GITORA_EVALUATION_TEST_KEY": "test-secret"}
        ):
            anthropic_provider, anthropic_model = ai_commit_eval.create_provider(
                anthropic_settings, "remote"
            )

        self.assertIsInstance(anthropic_provider, AnthropicMessagesProvider)
        self.assertEqual(anthropic_model, "claude-sonnet-4-20250514")

    def test_non_loopback_evaluation_stops_before_provider_creation(self) -> None:
        root = Path(self.temp_dir.name)
        manifest = root / "cases.jsonl"
        write_case_manifest(manifest, self.cases)
        args = SimpleNamespace(
            provider_kind="local",
            allow_remote_source_upload=False,
            cases=manifest,
            max_cases=1,
            repo=str(self.repo),
            results=root / "results.jsonl",
        )
        settings = self.settings.with_user_values({
            "local_endpoint": "http://192.168.1.20:11434",
        })

        with mock.patch.object(ai_commit_eval, "create_provider") as create:
            with self.assertRaisesRegex(EvaluationError, "源码上传确认"):
                ai_commit_eval.run(args, settings)

        create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
