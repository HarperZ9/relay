"""remote_cli.py — the ``python -m relay.remote_mcp`` entrypoint.

Loads a .env file (so secrets stay out of the process environment and out of
git), validates the public-URL config, and serves. Kept out of remote_mcp so
the transport module stays within the size gate.
"""
from __future__ import annotations

import os

from .remote_mcp import _ENDPOINT, config_from_env, serve


def _load_dotenv(path: str) -> dict[str, str]:
    """A tiny stdlib .env reader (KEY=value lines, # comments), so secrets live in
    a file instead of the process environment. No dependency; the real environment
    still wins over the file."""
    import pathlib

    file = pathlib.Path(path)
    if not file.exists():
        return {}
    values: dict[str, str] = {}
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    env = {**_load_dotenv(os.environ.get("RELAY_ENV_FILE", ".env")), **os.environ}
    cfg = config_from_env(env)
    if cfg is None:
        print("remote MCP is off: set RELAY_REMOTE_TOKEN (see .env.example)")
        return 2
    # A wrong public URL silently breaks Anthropic's on-origin OAuth discovery, so
    # fail fast rather than serve an unreachable connector.
    if cfg.oauth is not None and not cfg.oauth.base_url.startswith("https://"):
        print(f"error: RELAY_PUBLIC_URL must be an https origin, got {cfg.oauth.base_url!r}")
        return 2
    host = env.get("RELAY_REMOTE_HOST", "127.0.0.1")
    port = int(env.get("RELAY_REMOTE_PORT", "8787"))
    certfile = env.get("RELAY_TLS_CERT") or None
    keyfile = env.get("RELAY_TLS_KEY") or None
    server = serve(cfg, host, port, certfile=certfile, keyfile=keyfile)
    scheme = "https" if certfile and keyfile else "http"
    print(f"relay remote MCP on {scheme}://{host}:{port}{_ENDPOINT} "
          f"(exec {'on' if cfg.allow_remote_exec else 'off'}, "
          f"origins {'any' if not cfg.allowed_origins else len(cfg.allowed_origins)}, "
          f"oauth {'on' if cfg.oauth is not None else 'off'}, tls {scheme == 'https'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0
