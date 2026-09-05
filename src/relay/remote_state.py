"""remote_state.py -- whether a phone could reach this workstation, and on what terms.

The remote MCP surface runs as its own process (``python -m relay.remote_mcp``),
so nothing talking to the local stdio server can tell whether it is configured at
all. A client that offers "remote access" and cannot say this is guessing.

This reads the same two sources ``remote_cli`` composes, the env file and the
real environment, and reports without handing back a secret: a value comes back
only for the keys on VALUE_SAFE, and every other key the surface reads is
reported as a boolean.

The half-configured case is the one worth naming. ``_oauth_from_env`` returns
None unless all six of its keys are set, and the server then serves the static
bearer with no phone connector and says nothing about why. Here that reads as
oauth off with the missing keys named.
"""
from __future__ import annotations

import os
import pathlib
from typing import Mapping

DEFAULT_ENV_FILE = ".env"

# The keys whose values may leave this module. A public URL is the address you
# hand the phone; the listen host, port, origin list and exec flag describe what
# the surface would do. None of them is a credential.
VALUE_SAFE = frozenset({
    "RELAY_PUBLIC_URL", "RELAY_REMOTE_HOST", "RELAY_REMOTE_PORT",
    "RELAY_ALLOWED_ORIGINS", "RELAY_ALLOW_REMOTE_EXEC",
})

# Every other key the remote surface reads. Presence is all that is reported for
# these, whether or not the key happens to hold something secret today.
PRESENCE_ONLY = (
    "RELAY_REMOTE_TOKEN", "RELAY_OAUTH_CLIENT_ID", "RELAY_OAUTH_CLIENT_SECRET",
    "RELAY_OAUTH_SIGNING_SECRET", "RELAY_AUTHORIZE_PASSWORD",
    "RELAY_OAUTH_REDIRECT_URIS", "RELAY_TLS_CERT", "RELAY_TLS_KEY",
)

# What ``_oauth_from_env`` demands before the phone connector exists at all. Miss
# one and the surface still serves, with the static bearer only.
OAUTH_REQUIRED = (
    "RELAY_OAUTH_CLIENT_ID", "RELAY_OAUTH_CLIENT_SECRET",
    "RELAY_OAUTH_SIGNING_SECRET", "RELAY_PUBLIC_URL",
    "RELAY_AUTHORIZE_PASSWORD", "RELAY_OAUTH_REDIRECT_URIS",
)

_TRUE = ("1", "true", "yes")


def load_dotenv(path: str) -> dict[str, str]:
    """A tiny stdlib .env reader (KEY=value lines, # comments), so secrets live in
    a file instead of the process environment. No dependency; the real environment
    still wins over the file."""
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


def env_file_path(env: Mapping[str, str] | None = None) -> str:
    """The file the remote entrypoint would read, RELAY_ENV_FILE or ``.env``."""
    env = os.environ if env is None else env
    return env.get("RELAY_ENV_FILE") or DEFAULT_ENV_FILE


def resolved_env(env: Mapping[str, str] | None = None,
                 env_file: str | None = None) -> tuple[dict[str, str], str]:
    """The environment the remote server would see, and the file consulted.

    Composed exactly as ``remote_cli.main`` composes it: the file first, the real
    environment over it. A caller that passes ``env`` is asking about that
    environment rather than this process's.
    """
    env = dict(os.environ if env is None else env)
    path = env_file if env_file is not None else env_file_path(env)
    return {**load_dotenv(path), **env}, path


def _origins(raw: str) -> list[str]:
    return sorted({o.strip() for o in raw.split(",") if o.strip()})


def remote_state(env: Mapping[str, str] | None = None,
                 env_file: str | None = None) -> dict:
    """What the phone-facing surface is configured to do, values withheld.

    ``configured`` answers the only question that gates everything else: with no
    RELAY_REMOTE_TOKEN the entrypoint prints its notice and exits, so nothing
    remote is running whatever else is set.
    """
    resolved, path = resolved_env(env, env_file)
    present = {k: bool(resolved.get(k)) for k in PRESENCE_ONLY}
    missing_oauth = [k for k in OAUTH_REQUIRED if not resolved.get(k)]
    configured = present["RELAY_REMOTE_TOKEN"]
    state = {
        "configured": configured,
        "reason": "" if configured
                  else "RELAY_REMOTE_TOKEN is unset, so the remote surface stays off",
        "env_file": path,
        "env_file_found": pathlib.Path(path).exists(),
        "oauth_configured": not missing_oauth,
        # Named, never valued: which keys the phone connector is still waiting on.
        "oauth_missing": missing_oauth,
        "tls_configured": present["RELAY_TLS_CERT"] and present["RELAY_TLS_KEY"],
        "remote_exec_allowed": resolved.get("RELAY_ALLOW_REMOTE_EXEC", "").lower() in _TRUE,
        "public_url": resolved.get("RELAY_PUBLIC_URL") or None,
        "allowed_origins": _origins(resolved.get("RELAY_ALLOWED_ORIGINS", "")),
        "listen": {"host": resolved.get("RELAY_REMOTE_HOST") or None,
                   "port": resolved.get("RELAY_REMOTE_PORT") or None},
        "keys_present": present,
    }
    return state
