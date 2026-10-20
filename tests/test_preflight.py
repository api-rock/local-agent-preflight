from __future__ import annotations

import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent_preflight.cli import main
from agent_preflight.models import CheckResult, Report, Status
from agent_preflight.probes import probe_endpoint, run_bounded


class MockRuntimeHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, payload: dict[str, object], status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/api/tags":
            self._send({"models": [{"name": "tiny-model"}]})
            return
        self._send({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path == "/api/generate":
            self._send({"response": "OK", "done": True})
            return
        self._send({"error": "not found"}, status=404)


class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockRuntimeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.thread.join(timeout=2)
        cls.server.server_close()

    def test_endpoint_and_model_are_ready(self) -> None:
        result = probe_endpoint(self.url, model="tiny-model", smoke_test=True)
        self.assertEqual(result.status, Status.READY)
        self.assertIn("tiny-model", result.data["models"])

    def test_missing_model_blocks_without_running_inference(self) -> None:
        result = probe_endpoint(self.url, model="missing-model")
        self.assertEqual(result.status, Status.BLOCKED)
        self.assertIn("not found", result.summary)

    def test_invalid_url_is_blocked(self) -> None:
        result = probe_endpoint("not-a-url")
        self.assertEqual(result.status, Status.BLOCKED)
        self.assertIsNotNone(result.remediation)

    def test_command_timeout_is_bounded(self) -> None:
        result = run_bounded(
            [sys.executable, "-c", "import time; time.sleep(0.2)"],
            timeout=0.01,
        )
        self.assertTrue(result.timed_out)
        self.assertEqual(result.returncode, -1)

    def test_report_exit_codes(self) -> None:
        report = Report(
            [
                CheckResult("one", "test", Status.READY, "ready"),
                CheckResult("two", "test", Status.WARNING, "warning"),
            ]
        )
        self.assertEqual(report.exit_code(), 0)
        self.assertEqual(report.exit_code(strict=True), 1)

    def test_cli_emits_json_with_endpoint_result(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "check",
                    "--json",
                    "--url",
                    self.url,
                    "--model",
                    "tiny-model",
                ]
            )
        document = json.loads(output.getvalue())
        self.assertEqual(document["schema_version"], 1)
        self.assertIn(code, (0, 1))
        endpoint_results = [
            item for item in document["results"] if item["id"] == "api.endpoint"
        ]
        self.assertEqual(len(endpoint_results), 1)
        self.assertEqual(endpoint_results[0]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
