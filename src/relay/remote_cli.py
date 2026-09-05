"""remote_cli.py — the ``python -m relay.remote_mcp`` entrypoint.

Loads a .env file (so secrets stay out of the process environment and out of
git), validates the public-URL config, and serves. Kept out of remote_mcp so
the transport module stays within the size gate.
"""
from __future__ import annotations

from .remote_mcp import _ENDPOINT, config_from_env, serve
from .remote_state import resolved_env


def main() -> int:
    # Composed by remote_state, so the readout a client asks for is derived
    # from the same environment this entrypoint actually serves.
    env, _ = resolved_env()
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
