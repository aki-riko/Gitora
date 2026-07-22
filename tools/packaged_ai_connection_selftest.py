# coding: utf-8
"""用隔离配置和回环 Ollama stub 验证打包态 AI 连接路径。"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Sequence


MODEL_NAME = "gitora-packaged-selftest"
QML_MARKER = "rootObjects ="
CONNECTION_MARKER = "AI 连接检测成功"
SETTINGS_MARKER = "设置页导航成功"
CREDENTIAL_MARKER = "系统凭据库验证成功"


class PackagedSelftestError(RuntimeError):
    """打包程序未完成 QML 或 AI 连接自检。"""


class _OllamaStubHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self.server.model_requests += 1  # type: ignore[attr-defined]
        body = json.dumps({"data": [{"id": MODEL_NAME}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args) -> None:
        return


def _settings_path(root: Path) -> Path:
    if os.name == "nt":
        return root / "Gitora" / "ai_commit.json"
    return root / ".config" / "Gitora" / "ai_commit.json"


def _write_settings(root: Path, endpoint: str) -> Path:
    target = _settings_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "enabled": True,
                "provider": "ollama",
                "local_endpoint": endpoint,
                "local_model": MODEL_NAME,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


def _build_environment(root: Path, endpoint: str) -> dict[str, str]:
    _write_settings(root, endpoint)
    environment = os.environ.copy()
    environment.update(
        {
            "LOCALAPPDATA": str(root),
            "HOME": str(root),
            "GITESS_QML_SELFTEST": "1",
            "GITESS_AI_CONNECTION_SELFTEST": "1",
            "GITESS_SETTINGS_NAV_SELFTEST": "1",
            "GITESS_CREDENTIAL_SELFTEST": "1",
            "QT_QPA_PLATFORM": "offscreen",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return environment


def _run_executable(
    executable: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> subprocess.CompletedProcess[str]:
    resolved_executable = executable.resolve(strict=True)
    try:
        return runner(
            [str(resolved_executable)], cwd=str(resolved_executable.parent),
            env=environment,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout_seconds, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PackagedSelftestError("打包程序连接自检超时") from exc


def _validated_output(
    completed: subprocess.CompletedProcess[str], model_requests: int
) -> str:
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise PackagedSelftestError(
            f"打包程序连接自检退出码为 {completed.returncode}\n{output}"
        )
    if model_requests < 1:
        raise PackagedSelftestError("打包程序未访问回环模型列表端点")
    missing = [
        marker
        for marker in (
            QML_MARKER, SETTINGS_MARKER, CONNECTION_MARKER, CREDENTIAL_MARKER
        )
        if marker not in output
    ]
    if missing:
        raise PackagedSelftestError(
            f"打包程序连接自检缺少标志: {', '.join(missing)}\n{output}"
        )
    return output


def run_connection_selftest(
    executable: Path,
    timeout_seconds: int = 30,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    if not executable.is_file():
        raise PackagedSelftestError(f"未找到打包程序: {executable}")
    if timeout_seconds <= 0:
        raise ValueError("自检超时必须为正整数")

    server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaStubHandler)
    server.model_requests = 0  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="gitora-packaged-ai-") as temp_dir:
            isolated_root = Path(temp_dir)
            endpoint = f"http://127.0.0.1:{server.server_port}"
            environment = _build_environment(isolated_root, endpoint)
            completed = _run_executable(
                executable, environment, timeout_seconds, runner
            )
            model_requests = server.model_requests  # type: ignore[attr-defined]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return _validated_output(completed, model_requests)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    return parser


def _configure_console_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_console_output()
    args = build_parser().parse_args(argv)
    try:
        output = run_connection_selftest(args.executable, args.timeout_seconds)
    except (PackagedSelftestError, OSError, ValueError) as exc:
        print(f"[SELFTEST] 打包态 AI 连接验证失败: {exc}")
        return 1
    print(output, end="" if output.endswith("\n") else "\n")
    print("[SELFTEST] 打包态 AI 连接验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
