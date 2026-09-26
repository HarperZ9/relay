"""mcp_grants.py -- write and exec grants for the MCP servers, set at launch.

The process that starts a relay MCP server decides whether its runs may write
or execute, with ``--allow-write`` / ``--allow-exec`` or ``RELAY_ALLOW_WRITE`` /
``RELAY_ALLOW_EXEC``. Both are off by default. A tool call can only narrow what
the launch granted: its ``allow_write`` / ``allow_exec`` arguments turn a grant
off for one run and never turn one on.

Two couplings follow from what a shell can do. Exec implies write, because a
shell can write files. Narrowing write also turns exec off, for the same reason.

The honest limit: the file tools are confined to the run's root, and the shell
is not. ``run``, ``test_cmd`` and ``check`` start in root and can reach any path
the server's user can.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

WRITE_ENV = "RELAY_ALLOW_WRITE"
EXEC_ENV = "RELAY_ALLOW_EXEC"

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"", "0", "false", "no", "off"})


@dataclass(frozen=True)
class StartGrants:
    """What a server's runs may do at most. Exec implies write."""
    allow_write: bool = False
    allow_exec: bool = False

    def __post_init__(self) -> None:
        if self.allow_exec and not self.allow_write:
            object.__setattr__(self, "allow_write", True)

    def as_dict(self) -> dict:
        return {"allow_write": self.allow_write, "allow_exec": self.allow_exec,
                "shell_path_confined": False}


def parse_flag(env: Mapping[str, str], name: str) -> bool:
    """Read one grant variable. An unrecognized value raises instead of guessing,
    so a typo cannot silently leave a grant on or off."""
    raw = (env.get(name) or "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ValueError(f"{name} must be one of 1/true/yes/on or 0/false/no/off, got {raw!r}")


def grants_from_env(env: Mapping[str, str]) -> StartGrants:
    return StartGrants(allow_write=parse_flag(env, WRITE_ENV),
                       allow_exec=parse_flag(env, EXEC_ENV))


def grants_from_launch(*, allow_write: bool, allow_exec: bool,
                       env: Mapping[str, str]) -> StartGrants:
    """Flags or environment: either one grants."""
    from_env = grants_from_env(env)
    return StartGrants(allow_write=allow_write or from_env.allow_write,
                       allow_exec=allow_exec or from_env.allow_exec)


def narrow(grants: StartGrants, want_write: bool | None,
           want_exec: bool | None) -> tuple[bool, bool]:
    """The effective (write, exec) for one run. ``None`` means the argument was
    omitted and the launch grant stands; ``False`` turns it off; ``True`` asks
    for no more than the launch granted."""
    write = grants.allow_write and want_write is not False
    exec_ = grants.allow_exec and want_exec is not False and write
    return write, exec_


def describe(grants: StartGrants) -> str:
    """One line for a launcher's stderr."""
    def state(on: bool) -> str:
        return "granted" if on else "off"
    return (f"write {state(grants.allow_write)}, exec {state(grants.allow_exec)}"
            + (" (the shell is not path-confined)" if grants.allow_exec else ""))
