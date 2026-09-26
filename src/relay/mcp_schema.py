"""mcp_schema.py -- the tool list relay's MCP servers advertise.

Kept apart from local_mcp so the transport module stays within the size gate.
The run and start descriptions carry the grant model and the shell's
path-confinement limit, because an auto-consuming client reads them as the
contract.
"""
from __future__ import annotations

_ONLINE = {"online": {"type": "boolean", "description": "include codex/claude/gemini/deepseek"}}
_RUN_ID = {"type": "object", "required": ["run_id"], "properties": {"run_id": {"type": "string"}}}
_RUN_OPTIONS = {
    "backend": {"type": "string", "description": "preferred backend name, or auto"},
    "model": {"type": "string", "description": "model hint passed to model-aware backends"},
    "max_tokens": {"type": "integer", "description": "per-turn generation token cap"},
    "check": {"type": "string", "description": "acceptance command run once through a shell at the end; needs the exec grant"},
    "test_cmd": {"type": "string", "description": "test command run through the gated run tool when no tool calls run; needs the exec grant"},
    "compact_budget": {"type": "integer", "description": "optional prompt compaction budget"},
}
_RUN_ARGS = {"type": "object", "required": ["goal"],
             "properties": {"goal": {"type": "string"}, "root": {"type": "string"},
                            "allow_write": {"type": "boolean", "description": "narrow only: false turns write (and exec) off for this run; true cannot grant what the server was not started with"},
                            "allow_exec": {"type": "boolean", "description": "narrow only: false turns exec off for this run; true cannot grant what the server was not started with"},
                            "max_steps": {"type": "integer"}, **_RUN_OPTIONS, **_ONLINE}}

_GRANT_NOTE = (
    "Write and exec come from how the server was started (--allow-write / --allow-exec, or "
    "RELAY_ALLOW_WRITE / RELAY_ALLOW_EXEC); both are off by default. The allow_write and "
    "allow_exec arguments can only narrow those grants for one run, never widen them. Exec "
    "implies write, and allow_write=false also turns exec off. check runs a shell, so it needs "
    "the exec grant. File tools (read/list/write) are confined to root. The shell is NOT "
    "path-confined: run, test_cmd and check start in root and can reach any path the server's "
    "user can.")

TOOLS = [
    {"name": "local_agent_health",
     "description": "Report which model tiers are live (local serve/ollama, plus online providers when online=true).",
     "inputSchema": {"type": "object", "properties": dict(_ONLINE)}},
    {"name": "local_agent_chat",
     "description": "One-shot completion from the first healthy tier, with a per-turn receipt.",
     "inputSchema": {"type": "object", "required": ["prompt"],
                     "properties": {"prompt": {"type": "string"},
                                    "backend": {"type": "string"}, **_ONLINE}}},
    {"name": "local_agent_run",
     "description": "Run a gated agentic task and return the final answer and a verifiable ledger checkpoint. " + _GRANT_NOTE + " BLOCKS until done; from a phone or a flaky link, prefer local_agent_start.",
     "inputSchema": _RUN_ARGS},
    {"name": "local_agent_start",
     "description": "Start a gated agentic task in the BACKGROUND and return a run_id at once (does not block). " + _GRANT_NOTE + " Poll local_agent_status for live progress, then local_agent_result for the verified final answer. With RELAY_RUN_ROOT, witnessed progress checkpoints survive a restart as interrupted partial runs. Use this from a phone or over a flaky network, where a blocking run would drop.",
     "inputSchema": _RUN_ARGS},
    {"name": "local_agent_status",
     "description": "Progress of a background run: state (running/done/error/interrupted), the step count so far, and the latest witnessed ledger entries.",
     "inputSchema": _RUN_ID},
    {"name": "local_agent_result",
     "description": "The verified final answer and ledger checkpoint of a background run once it is done; reports 'running' until then.",
     "inputSchema": _RUN_ID},
    {"name": "local_agent_runs",
     "description": "List recent background runs (newest first) with state, timing, and step count, so a phone that lost a run_id after a restart can find it again. Persisted runs (RELAY_RUN_ROOT) survive a restart; a run cut off mid-flight lists as 'interrupted'.",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 0}}}},
    {"name": "local_agent_sessions",
     "description": "List saved relay sessions (witnessed ledgers under RELAY_SESSION_DIR) so a session started on the PC can be reopened from another device; each is re-verified on load. Pass session_id to get that session's transcript.",
     "inputSchema": {"type": "object", "properties": {"session_id": {"type": "string"}}}},
    {"name": "relay.status",
     "description": "Liveness and identity of the relay MCP server (name, version, protocol). Network-free, for a fast health probe.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "relay.doctor",
     "description": "Readiness diagnostic: identity plus the local model tiers configured (serve, ollama) and the tools exposed. Network-free; use local_agent_health to actually ping tiers.",
     "inputSchema": {"type": "object", "properties": {}}},
]
