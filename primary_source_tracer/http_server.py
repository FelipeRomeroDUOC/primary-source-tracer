"""Stateless Streamable HTTP transport for Primary Source Tracer MCP server."""

from __future__ import annotations

import hmac
import json
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

MAX_HTTP_BODY_BYTES = 1_048_576  # 1 MiB


def create_mcp_http_server(
    host: str,
    port: int,
    request_handler: Callable[[dict, bool], dict | None],
    auth_token: str = "",
    remote_safe: bool = True,
) -> ThreadingHTTPServer:
    """Create a ThreadingHTTPServer serving MCP Streamable HTTP on /mcp and /healthz."""
    expected_token = (auth_token or "").strip()

    class _MCPHTTPHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            sys.stderr.write(f"[http] {self.address_string()} - {format % args}\n")

        def _write_cors_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, DELETE")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, Accept, Mcp-Session-Id, MCP-Protocol-Version",
            )

        def _send_json(self, status: int, payload: object, extra_headers: dict[str, str] | None = None) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._write_cors_headers()
            for key, val in (extra_headers or {}).items():
                self.send_header(key, val)
            self.end_headers()
            self.wfile.write(body)

        def _send_empty(self, status: int, extra_headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self._write_cors_headers()
            for key, val in (extra_headers or {}).items():
                self.send_header(key, val)
            self.end_headers()

        def _check_auth(self) -> bool:
            if not expected_token:
                return True
            header = (self.headers.get("Authorization") or "").strip()
            prefix = "Bearer "
            if not header.startswith(prefix):
                self._send_json(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "Unauthorized: Bearer token required."},
                    {"WWW-Authenticate": "Bearer"},
                )
                return False
            provided = header[len(prefix) :].strip()
            if not hmac.compare_digest(provided, expected_token):
                self._send_json(
                    HTTPStatus.UNAUTHORIZED,
                    {"error": "Unauthorized: Invalid Bearer token."},
                    {"WWW-Authenticate": "Bearer"},
                )
                return False
            return True

        def _clean_path(self) -> str:
            return self.path.split("?", 1)[0].rstrip("/") or "/"

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send_empty(HTTPStatus.NO_CONTENT)

        def do_GET(self) -> None:  # noqa: N802
            path = self._clean_path()
            if path in ("/healthz", "/"):
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "server": "primary-source-tracer",
                        "transport": "streamable-http",
                        "remote_safe": remote_safe,
                    },
                )
                return
            if path == "/mcp":
                self._send_empty(HTTPStatus.METHOD_NOT_ALLOWED, {"Allow": "POST, OPTIONS, DELETE"})
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_DELETE(self) -> None:  # noqa: N802
            if self._clean_path() == "/mcp":
                if not self._check_auth():
                    return
                self._send_empty(HTTPStatus.NO_CONTENT)
                return
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self._clean_path() != "/mcp":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
                return
            if not self._check_auth():
                return

            try:
                content_length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
                return
            if content_length <= 0:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Empty request body"})
                return
            if content_length > MAX_HTTP_BODY_BYTES:
                self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Payload too large"})
                return

            raw_body = self.rfile.read(content_length)
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                )
                return

            if isinstance(payload, list):
                if not payload:
                    self._send_json(
                        HTTPStatus.BAD_REQUEST,
                        {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}},
                    )
                    return
                responses = []
                for item in payload:
                    if not isinstance(item, dict):
                        responses.append(
                            {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
                        )
                        continue
                    resp = request_handler(item, remote_safe)
                    if resp is not None:
                        responses.append(resp)
                if not responses:
                    self._send_empty(HTTPStatus.ACCEPTED)
                    return
                self._send_json(HTTPStatus.OK, responses)
                return

            if not isinstance(payload, dict):
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}},
                )
                return

            resp = request_handler(payload, remote_safe)
            if resp is None:
                self._send_empty(HTTPStatus.ACCEPTED)
                return
            self._send_json(HTTPStatus.OK, resp)

    return ThreadingHTTPServer((host, port), _MCPHTTPHandler)


def run_http_server(
    host: str,
    port: int,
    request_handler: Callable[[dict, bool], dict | None],
    auth_token: str = "",
    remote_safe: bool = True,
) -> None:
    """Start the Streamable HTTP MCP server and block until interrupted."""
    server = create_mcp_http_server(
        host=host,
        port=port,
        request_handler=request_handler,
        auth_token=auth_token,
        remote_safe=remote_safe,
    )
    if not (auth_token or "").strip():
        sys.stderr.write(
            "[primary-source-tracer] WARNING: --http iniciado sin MCP_AUTH_TOKEN/--auth-token. "
            "No lo expongas públicamente sin autenticación.\n"
        )
    sys.stderr.write(
        f"[primary-source-tracer] Streamable HTTP MCP escuchando en http://{host}:{port}/mcp "
        f"(remote_safe={remote_safe})\n"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
