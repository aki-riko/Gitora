# coding: utf-8
from __future__ import annotations

import json
import os
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch

from app.common.ai_commit_http import (
    endpoint_requires_remote_consent,
    HttpJsonClient,
    HttpProviderConfig,
    HttpProviderError,
    OllamaProvider,
    OpenAIResponsesProvider,
)
from app.common.ai_commit_models import (
    ChangeSnapshot,
    FileChangeSnapshot,
    PlannerRequest,
)


def make_request() -> PlannerRequest:
    change = FileChangeSnapshot(
        "file_1", "src/main.py", "src/main.py", "src/main.py", "M", True,
        False, False, "", 1, 1, "diff --git a/src/main.py b/src/main.py\n", (),
    )
    snapshot = ChangeSnapshot(
        "snapshot-1", "workspace-1", "repo-token", "head", "master",
        False, True, (change,), recent_titles=("fix: 旧提交",),
    )
    return PlannerRequest(snapshot, "message", "file")


def plan_payload() -> dict:
    return {
        "schema_version": "1",
        "snapshot_id": "snapshot-1",
        "level": "file",
        "summary": "修改入口",
        "groups": [{
            "group_id": "main",
            "title": "fix: 修改入口",
            "body": "补充说明",
            "change_ids": ["file_1"],
            "depends_on": [],
            "rationale": "单一改动",
            "warnings": [],
        }],
        "unassigned_change_ids": [],
        "warnings": [],
    }


class _OllamaHandler(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, dict | None]] = []

    def do_GET(self) -> None:  # noqa: N802
        self.__class__.requests.append(("GET", self.path, None))
        self._send({"data": [{"id": "local-model"}]})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.requests.append(("POST", self.path, payload))
        self._send({
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps(plan_payload()),
                },
            }],
        })

    def _send(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args) -> None:
        return


class _ProxyCaptureHandler(_OllamaHandler):
    requests: list[tuple[str, str, dict | None]] = []


class _FakeResponse:
    def __init__(self, payload: dict):
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount: int) -> bytes:
        return self.body[:amount]


class AiCommitHttpTest(unittest.TestCase):
    def test_endpoint_remote_consent_classification_is_loopback_only(self) -> None:
        cases = {
            "http://localhost:11434": False,
            "http://LOCALHOST.:11434": False,
            "http://127.0.0.1:11434": False,
            "http://127.42.0.9:11434": False,
            "http://[::1]:11434": False,
            "http://192.168.1.20:11434": True,
            "https://ollama.example.com": True,
            "http://[2001:db8::1]:11434": True,
            "not-a-url": True,
        }
        for endpoint, expected in cases.items():
            with self.subTest(endpoint=endpoint):
                self.assertEqual(
                    endpoint_requires_remote_consent(endpoint), expected
                )

    def test_local_provider_uses_openai_compatible_schema_and_endpoints(self) -> None:
        _OllamaHandler.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        provider = OllamaProvider(HttpProviderConfig(base, "local-model", "", 5, 100_000))

        self.assertEqual(provider.list_models(), ("local-model",))
        result = provider.generate_plan(make_request())

        self.assertEqual(result["snapshot_id"], "snapshot-1")
        post = next(item for item in _OllamaHandler.requests if item[0] == "POST")
        self.assertEqual(post[1], "/v1/chat/completions")
        self.assertFalse(post[2]["stream"])
        response_format = post[2]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(response_format["json_schema"]["name"], "gitora_commit_plan")
        self.assertTrue(response_format["json_schema"]["strict"])
        schema = response_format["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        change_enum = schema["properties"]["groups"]["items"]["properties"]["change_ids"]["items"]["enum"]
        self.assertEqual(change_enum, ["file_1"])

    def test_loopback_ollama_bypasses_environment_proxy(self) -> None:
        _OllamaHandler.requests = []
        _ProxyCaptureHandler.requests = []
        target = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaHandler)
        proxy = ThreadingHTTPServer(("127.0.0.1", 0), _ProxyCaptureHandler)
        for server in (target, proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)

        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        environment = {
            "HTTP_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "NO_PROXY": "",
            "no_proxy": "",
        }
        endpoint = f"http://127.0.0.1:{target.server_port}"
        with patch.dict(os.environ, environment):
            provider = OllamaProvider(HttpProviderConfig(
                endpoint, "local-model", "", 5, 100_000
            ))
            self.assertEqual(provider.list_models(), ("local-model",))

        self.assertEqual(_ProxyCaptureHandler.requests, [])
        self.assertIn(("GET", "/v1/models", None), _OllamaHandler.requests)

    def test_openai_responses_uses_structured_output_and_bearer_auth(self) -> None:
        output = {
            "output": [{
                "type": "message",
                "content": [{
                    "type": "output_text",
                    "text": json.dumps(plan_payload()),
                }],
            }]
        }
        config = HttpProviderConfig(
            "https://example.invalid/v1/responses", "remote-model", "top-secret", 5, 100_000
        )
        fake_opener = Mock()
        fake_opener.open.return_value = _FakeResponse(output)
        provider = OpenAIResponsesProvider(config)
        provider._client = HttpJsonClient(5, 100_000, opener=fake_opener)
        result = provider.generate_plan(make_request())

        self.assertEqual(result["groups"][0]["title"], "fix: 修改入口")
        request = fake_opener.open.call_args.args[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, config.endpoint)
        self.assertEqual(request.headers["Authorization"], "Bearer top-secret")
        self.assertEqual(body["text"]["format"]["type"], "json_schema")
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertNotIn("repo-token", body["input"])

    def test_openai_lists_models_from_responses_sibling_with_bearer_auth(self) -> None:
        config = HttpProviderConfig(
            "https://example.invalid/v1/responses",
            "remote-model",
            "top-secret",
            5,
            100_000,
        )
        fake_opener = Mock()
        fake_opener.open.return_value = _FakeResponse({
            "object": "list",
            "data": [
                {"id": "model-b"},
                {"id": "model-a"},
                {"id": "model-b"},
            ],
        })
        provider = OpenAIResponsesProvider(config)
        provider._client = HttpJsonClient(5, 100_000, opener=fake_opener)

        self.assertEqual(provider.list_models(), ("model-b", "model-a"))
        request = fake_opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.invalid/v1/models")
        self.assertEqual(request.headers["Authorization"], "Bearer top-secret")
        self.assertIsNone(request.data)

    def test_openai_model_list_requires_responses_endpoint_path(self) -> None:
        provider = OpenAIResponsesProvider(HttpProviderConfig(
            "https://example.invalid/custom/generate", "model", "key", 5, 1000
        ))

        with self.assertRaisesRegex(HttpProviderError, "以 /responses 结尾"):
            provider.list_models()

    def test_remote_provider_rejects_insecure_or_embedded_credential_url(self) -> None:
        for endpoint in (
            "http://example.com/v1/responses",
            "https://user:pass@example.com/v1/responses",
            "https://example.com/v1/responses?key=value",
        ):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(HttpProviderError):
                    OpenAIResponsesProvider(
                        HttpProviderConfig(endpoint, "model", "key", 5, 1000)
                    )

    def test_http_error_does_not_echo_key_or_source(self) -> None:
        error = urllib.error.HTTPError(
            "https://example.invalid/v1/responses", 401, "Unauthorized", {}, None
        )
        config = HttpProviderConfig(
            "https://example.invalid/v1/responses", "model", "top-secret", 5, 100_000
        )
        fake_opener = Mock()
        fake_opener.open.side_effect = error
        provider = OpenAIResponsesProvider(config)
        provider._client = HttpJsonClient(5, 100_000, opener=fake_opener)
        with self.assertRaises(HttpProviderError) as caught:
            provider.generate_plan(make_request())
        message = str(caught.exception)
        self.assertNotIn("top-secret", message)
        self.assertNotIn("src/main.py", message)
        self.assertIn("HTTP 401", message)

    def test_client_does_not_follow_redirects(self) -> None:
        redirect = urllib.error.HTTPError(
            "https://example.invalid/v1/responses", 302, "Found", {}, None
        )
        fake_opener = Mock()
        fake_opener.open.side_effect = redirect
        client = HttpJsonClient(5, 1000, opener=fake_opener)
        with self.assertRaisesRegex(HttpProviderError, "HTTP 302"):
            client.request("GET", "https://example.invalid/v1/responses")
        self.assertEqual(fake_opener.open.call_count, 1)

    def test_message_schema_limits_groups_and_can_disable_body(self) -> None:
        request = make_request()
        request = PlannerRequest(
            request.snapshot, request.mode, request.level, generate_body=False
        )
        output = {
            "output_text": json.dumps(plan_payload()),
        }
        fake_opener = Mock()
        fake_opener.open.return_value = _FakeResponse(output)
        provider = OpenAIResponsesProvider(HttpProviderConfig(
            "https://example.invalid/v1/responses", "model", "key", 5, 100_000
        ))
        provider._client = HttpJsonClient(5, 100_000, opener=fake_opener)
        provider.generate_plan(request)
        body = json.loads(fake_opener.open.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(body["text"]["format"]["schema"]["properties"]["groups"]["maxItems"], 1)
        self.assertIn("body 必须返回空字符串", body["input"])


if __name__ == "__main__":
    unittest.main()
