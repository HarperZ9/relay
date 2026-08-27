"""remote_mcp.py — relay's MCP server over Streamable HTTP, for a remote client.

Wraps the transport-free ``local_mcp.handle()`` in the MCP Streamable HTTP
transport (protocol 2025-06-18): a single ``/mcp`` endpoint. A POST carrying one
JSON-RPC request returns one ``application/json`` response -- relay's run_agent
is blocking, so no SSE stream is needed for a usable v1; a POST carrying a
notification/response returns 202. GET returns 405 (relay opens no
server-initiated stream yet). This is what a phone MCP connector drives once the
endpoint is publicly reachable over HTTPS.

Safety posture, hardened versus the same-machine stdio server:
- every request must present the configured bearer token (constant-time check);
- when an allowlist is configured, the Origin header must be on it (the spec's
  DNS-rebinding guard);
- ``allow_exec`` is refused unless the operator opts in at the PC
  (RELAY_ALLOW_REMOTE_EXEC), because relay's run/exec is not root-confined.
``allow_write`` stays a per-call opt-in; the OAuth authorization layer is a later
increment (a bearer token gates v1).

``process()`` is transport-free and fully testable without a socket; the HTTP
handler and ``serve()`` are the thin transport around it.
"""
from __future__ import annotations

import hmac
import json
import os
from collections.abc import Callable, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .local_mcp import PROTOCOL, handle as _default_handle

_MAX_BODY = 1 << 20  # 1 MiB request-body cap
_ENDPOINT = "/mcp"


class RemoteMcpConfig:
    """The remote surface's policy: the bearer token, an optional Origin
    allowlist, whether remote exec is permitted, and the JSON-RPC handler
    (injectable for tests)."""

    def __init__(
        self,
        *,
        token: str,
        allowed_origins=frozenset(),
        allow_remote_exec: bool = False,
        handle: Callable[[dict], dict | None] | None = None,
    ) -> None:
        if not token:
            raise ValueError("a non-empty bearer token is required for the remote surface")
        self.token = token
        self.allowed_origins = frozenset(allowed_origins)
        self.allow_remote_exec = allow_remote_exec
        self.handle = handle or _default_handle


def config_from_env(env: Mapping[str, str] | None = None) -> RemoteMcpConfig | None:
    """Build a RemoteMcpConfig from the environment, or None when
    RELAY_REMOTE_TOKEN is unset (the remote surface stays off by default)."""
    env = os.environ if env is None else env
    token = env.get("RELAY_REMOTE_TOKEN")
    if not token:
        return None
    origins = {o.strip() for o in env.get("RELAY_ALLOWED_ORIGINS", "").split(",") if o.strip()}
    exec_ok = env.get("RELAY_ALLOW_REMOTE_EXEC", "").lower() in ("1", "true", "yes")
    return RemoteMcpConfig(token=token, allowed_origins=origins, allow_remote_exec=exec_ok)


def _json(status: int, obj) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "application/json"}, json.dumps(obj).encode("utf-8")


def _bearer_ok(authorization: str | None, token: str) -> bool:
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        return False
    return hmac.compare_digest(authorization[len(prefix):].strip(), token)


def _apply_remote_posture(cfg: RemoteMcpConfig, req: dict) -> None:
    """Refuse remote exec unless the operator opted in at the PC. relay's run/exec
    is not root-confined, so an allowed shell reaches outside root; on the remote
    surface allow_exec is forced off (the run still proceeds, without exec)."""
    if cfg.allow_remote_exec:
        return
    params = req.get("params") or {}
    if req.get("method") == "tools/call" and params.get("name") == "local_agent_run":
        args = params.get("arguments") or {}
        if args.get("allow_exec"):
            args["allow_exec"] = False
            params["arguments"] = args
            req["params"] = params


def process(
    cfg: RemoteMcpConfig, method: str, headers: Mapping[str, str], body: bytes
) -> tuple[int, dict, bytes]:
    """Handle one HTTP request to the MCP endpoint. Transport-free: returns
    (status, response_headers, response_body). ``headers`` keys are lowercase."""
    origin = headers.get("origin")
    if cfg.allowed_origins and origin is not None and origin not in cfg.allowed_origins:
        return _json(403, {"error": "origin not allowed"})
    if not _bearer_ok(headers.get("authorization"), cfg.token):
        return _json(401, {"error": "missing or invalid bearer token"})
    if method == "GET":
        # relay offers no server-initiated SSE stream on the endpoint yet
        return 405, {"Allow": "POST"}, b""
    if method != "POST":
        return _json(405, {"error": f"method {method} not allowed"})
    version = headers.get("mcp-protocol-version")
    if version is not None and version != PROTOCOL:
        return _json(400, {"error": f"unsupported MCP-Protocol-Version {version!r}"})
    if len(body) > _MAX_BODY:
        return _json(413, {"error": "request body too large"})
    try:
        req = json.loads(body)
    except json.JSONDecodeError:
        return _json(400, {"error": "body is not valid JSON-RPC"})
    if not isinstance(req, dict):
        return _json(400, {"error": "JSON-RPC message must be an object"})
    _apply_remote_posture(cfg, req)
    resp = cfg.handle(req)
    if resp is None:
        # a notification or response the server accepts carries no reply body
        return 202, {}, b""
    return _json(200, resp)


def make_handler(cfg: RemoteMcpConfig):
    class _Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method: str) -> None:
            if self.path.split("?", 1)[0] != _ENDPOINT:
                self._send(*_json(404, {"error": f"no endpoint {self.path!r}; use {_ENDPOINT}"}))
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY:
                self._send(*_json(413, {"error": "request body too large"}))
                return
            body = self.rfile.read(length) if length else b""
            lower = {k.lower(): v for k, v in self.headers.items()}
            self._send(*process(cfg, method, lower, body))

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_GET(self) -> None:
            self._dispatch("GET")

        def _send(self, status: int, headers: dict, body: bytes) -> None:
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def log_message(self, *args) -> None:  # keep the server quiet
            return None

    return _Handler


def serve(cfg: RemoteMcpConfig, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    """Build (do not start) a ThreadingHTTPServer for the remote MCP endpoint.

    Bind to localhost by default; a public deployment fronts this with TLS and a
    reverse tunnel rather than binding 0.0.0.0 directly. The caller runs
    ``serve_forever()``.
    """
    return ThreadingHTTPServer((host, port), make_handler(cfg))


def main() -> int:
    cfg = config_from_env()
    if cfg is None:
        print("remote MCP is off: set RELAY_REMOTE_TOKEN to enable it")
        return 2
    host = os.environ.get("RELAY_REMOTE_HOST", "127.0.0.1")
    port = int(os.environ.get("RELAY_REMOTE_PORT", "8787"))
    server = serve(cfg, host, port)
    print(f"relay remote MCP on http://{host}:{port}{_ENDPOINT} "
          f"(exec {'on' if cfg.allow_remote_exec else 'off'}, "
          f"origins {'any' if not cfg.allowed_origins else len(cfg.allowed_origins)})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
