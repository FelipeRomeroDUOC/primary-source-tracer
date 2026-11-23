import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from primary_source_tracer.http_server import create_mcp_http_server
from primary_source_tracer.server import (
    fetch_document,
    handle_jsonrpc_request,
    validate_public_http_url,
)


class _NoRaiseHTTPErrorProcessor(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        return response

    https_response = http_response


class TestHttpServerAndSSRF(unittest.TestCase):
    def setUp(self):
        self.server = create_mcp_http_server(
            host="127.0.0.1",
            port=0,
            request_handler=lambda req, safe: handle_jsonrpc_request(req, remote_safe=safe),
            auth_token="secret-test-token",
            remote_safe=True,
        )
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.opener = urllib.request.build_opener(_NoRaiseHTTPErrorProcessor())

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _request(self, method: str, path: str, body: dict | list | None = None, headers: dict | None = None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=req_headers,
            method=method,
        )
        with self.opener.open(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, dict(resp.headers), raw

    def test_1_ssrf_url_validator_blocks_private_and_local_targets(self):
        blocked = [
            "file:///etc/passwd",
            "/etc/hosts",
            "C:\\Windows\\System32\\drivers\\etc\\hosts",
            "http://localhost:8080/secret",
            "http://127.0.0.1:8000/mcp",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/internal",
            "http://192.168.1.1/admin",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://metadata.google.internal/computeMetadata/v1/",
        ]
        for target in blocked:
            self.assertIsNotNone(validate_public_http_url(target), f"Expected blocked: {target}")

        self.assertIsNone(validate_public_http_url("https://1.1.1.1/"))
        self.assertIsNone(validate_public_http_url("https://example.org/paper.pdf"))

    def test_2_remote_safe_blocks_existing_local_file_and_redirects(self):
        with tempfile.TemporaryDirectory() as d:
            local_html = Path(d) / "secret.html"
            local_html.write_text("<html><body>Secret local data</body></html>", encoding="utf-8")

            local_res = fetch_document(str(local_html), remote_safe=False)
            self.assertIsNone(local_res["error"])
            self.assertIn("Secret local data", local_res["text"])

            remote_res = fetch_document(str(local_html), remote_safe=True)
            self.assertIsNotNone(remote_res["error"])
            self.assertEqual(remote_res["text"], "")

            file_uri_res = fetch_document(local_html.as_uri(), remote_safe=True)
            self.assertIsNotNone(file_uri_res["error"])
            self.assertEqual(file_uri_res["text"], "")

    def test_3_http_healthz_auth_and_streamable_http_lifecycle(self):
        status, _, raw = self._request("GET", "/healthz")
        self.assertEqual(status, 200)
        health = json.loads(raw)
        self.assertEqual(health["transport"], "streamable-http")
        self.assertTrue(health["remote_safe"])

        status, resp_headers, _ = self._request("GET", "/mcp")
        self.assertEqual(status, 405)
        self.assertIn("POST", resp_headers.get("Allow", ""))

        status, _, _ = self._request("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(status, 401)

        auth = {"Authorization": "Bearer secret-test-token"}

        status, _, raw = self._request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            headers=auth,
        )
        self.assertEqual(status, 200)
        init_json = json.loads(raw)
        self.assertEqual(init_json["result"]["serverInfo"]["name"], "primary-source-tracer")

        status, _, raw = self._request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=auth,
        )
        self.assertEqual(status, 202)
        self.assertEqual(raw, "")

        status, _, raw = self._request(
            "POST",
            "/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=auth,
        )
        self.assertEqual(status, 200)
        tools_json = json.loads(raw)
        self.assertEqual(len(tools_json["result"]["tools"]), 3)

    def test_4_http_tool_call_blocks_ssrf_metadata_url(self):
        auth = {"Authorization": "Bearer secret-test-token"}
        status, _, raw = self._request(
            "POST",
            "/mcp",
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "inspect_and_classify_source",
                    "arguments": {
                        "url_or_path": "http://169.254.169.254/latest/meta-data/",
                        "agent_evidence_markers": ["ami-id"],
                    },
                },
            },
            headers=auth,
        )
        self.assertEqual(status, 200)
        rpc_resp = json.loads(raw)
        payload = json.loads(rpc_resp["result"]["content"][0]["text"])
        self.assertEqual(payload["preliminary_classification"], "unreachable_or_empty")
        self.assertTrue(any("bloqueada" in sig.lower() for sig in payload["friction_signals"]))


if __name__ == "__main__":
    unittest.main()
