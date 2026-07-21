# coding: utf-8
"""准备并运行 Gitora AI 提交规划器历史回放评测。"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.common.ai_commit_evaluation import (  # noqa: E402
    EvaluationError,
    EvaluationRunner,
    HistoryReplayBuilder,
    read_case_manifest,
    write_case_manifest,
    write_evaluation_records,
    write_manual_template,
)
from app.common.ai_commit_http import (  # noqa: E402
    HttpProviderConfig,
    OllamaProvider,
    OpenAIResponsesProvider,
)
from app.common.ai_commit_settings import (  # noqa: E402
    AiCommitSettings,
    AiCommitSettingsStore,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="可选的非敏感 AI 配置 JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="生成真实历史样本和人工评价表")
    prepare.add_argument("--repo", required=True)
    prepare.add_argument("--cases", required=True, type=Path)
    prepare.add_argument("--manual", required=True, type=Path)
    prepare.add_argument("--count", required=True, type=int)
    prepare.add_argument("--commits-per-case", required=True, type=int)

    run = subparsers.add_parser("run", help="调用配置的本地或远程模型")
    run.add_argument("--repo", required=True)
    run.add_argument("--cases", required=True, type=Path)
    run.add_argument("--results", required=True, type=Path)
    run.add_argument("--provider-kind", required=True, choices=("local", "remote"))
    run.add_argument("--allow-remote-source-upload", action="store_true")
    run.add_argument("--max-cases", type=int)
    return parser


def load_settings(config_path: Path | None) -> AiCommitSettings:
    store = AiCommitSettingsStore(config_path=config_path) if config_path else AiCommitSettingsStore()
    return store.load()


def create_provider(settings: AiCommitSettings, provider_kind: str):
    if provider_kind == "local":
        config = HttpProviderConfig(
            settings.local_endpoint,
            settings.local_model,
            "",
            settings.timeout_seconds,
            settings.max_response_chars,
        )
        return OllamaProvider(config), settings.local_model
    api_key = os.environ.get(settings.api_key_env, "") if settings.api_key_env else ""
    config = HttpProviderConfig(
        settings.remote_endpoint,
        settings.remote_model,
        api_key,
        settings.timeout_seconds,
        settings.max_response_chars,
    )
    return OpenAIResponsesProvider(config), settings.remote_model


def prepare(args, settings: AiCommitSettings) -> None:
    cases = HistoryReplayBuilder(
        args.repo, settings.timeout_seconds
    ).build(args.count, args.commits_per_case)
    write_case_manifest(args.cases, cases)
    write_manual_template(args.manual, cases)
    print(f"prepared_cases={len(cases)}")


def run(args, settings: AiCommitSettings) -> None:
    if args.provider_kind == "remote" and not args.allow_remote_source_upload:
        raise EvaluationError("远程评测必须显式传入源码上传确认参数")
    cases = read_case_manifest(args.cases)
    if args.max_cases is not None:
        if args.max_cases <= 0:
            raise EvaluationError("max-cases 必须为正整数")
        cases = cases[:args.max_cases]
    provider, model = create_provider(settings, args.provider_kind)
    runner = EvaluationRunner(
        args.repo, settings.limits, settings.timeout_seconds
    )
    records = [
        runner.run_case(case, provider, args.provider_kind, model)
        for case in cases
    ]
    write_evaluation_records(args.results, records)
    passed = sum(record.status == "passed" for record in records)
    print(f"evaluated_cases={len(records)} passed={passed}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        settings = load_settings(args.config)
        if args.command == "prepare":
            prepare(args, settings)
        else:
            run(args, settings)
    except (EvaluationError, OSError, ValueError) as exc:
        print(f"error={exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
