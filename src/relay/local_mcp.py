"""local_mcp.py — expose the local/multi-endpoint agent as an MCP server.

So any harness (Claude Code included) can call this agent as a tool: check which
tiers are live, get a one-shot completion, or run a gated agentic task with a
witnessed ledger. Zero-dep stdio JSON-RPC 2.0, the shape every flagship speaks.
`handle()` is transport-free and testable; `serve()` is the thin stdio loop.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

from .async_runs import RunRegistry
from .local_agent import LocalAgent, available_backends, health_report
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate
from .remote_state import remote_state

PROTOCOL = "2025-06-18"
__version__ = "0.2.5"

# Background runs, so a phone can start a long agentic task and poll it instead of
# holding one blocking HTTP request open across a flaky mobile network. With
# RELAY_RUN_ROOT set, runs persist so a run_id survives a server restart.
RUNS = RunRegistry(run_root=os.environ.get("RELAY_RUN_ROOT") or None)

_ONLINE = {"online": {"type": "boolean", "description": "include codex/claude/gemini/deepseek"}}
_RUN_ID = {"type": "object", "required": ["run_id"], "properties": {"run_id": {"type": "string"}}}
_RUN_OPTIONS = {
    "backend": {"type": "string", "description": "preferred backend name, or auto"},
    "model": {"type": "string", "description": "model hint passed to model-aware backends"},
    "max_tokens": {"type": "integer", "description": "per-turn generation token cap"},
    "check": {"type": "string", "description": "acceptance command to run through the gated executor"},
    "test_cmd": {"type": "string", "description": "fallback test command when no tool calls run"},
    "compact_budget": {"type": "integer", "description": "optional prompt compaction budget"},
}
_RUN_ARGS = {"type": "object", "required": ["goal"],
             "properties": {"goal": {"type": "string"}, "root": {"type": "string"},
                            "allow_write": {"type": "boolean"}, "allow_exec": {"type": "boolean"},
                            "max_steps": {"type": "integer"}, **_RUN_OPTIONS, **_ONLINE}}

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
     "description": "Run a gated agentic task; write/exec off unless allowed. File tools (read/list/write) are confined to root; run/exec sets only cwd, so an allowed shell is NOT path-confined and can reach outside root. allow_exec implies write (a shell can write). Returns the final answer and a verifiable ledger checkpoint. BLOCKS until done -- for a phone or a flaky link, prefer local_agent_start.",
     "inputSchema": _RUN_ARGS},
    {"name": "local_agent_start",
     "description": "Start a gated agentic task in the BACKGROUND and return a run_id at once (does not block). Same gate as local_agent_run (write/exec off unless allowed). Poll local_agent_status for live progress, then local_agent_result for the verified final answer. With RELAY_RUN_ROOT, witnessed progress checkpoints survive a restart as interrupted partial runs. Use this from a phone or over a flaky network, where a blocking run would drop.",
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


class MCPInputError(ValueError):
    """Typed user/request error returned as JSON instead of an opaque traceback."""

    def __init__(self, code: str, message: str, *, request_binding: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.request_binding = request_binding


def _as_bool(args: dict, name: str) -> bool:
    val = args.get(name, False)
    if type(val) is bool:
        return val
    raise MCPInputError("INVALID_ARGUMENT", f"{name} must be a boolean")


def _as_int(args: dict, name: str, default: int) -> int:
    val = args.get(name, default)
    if type(val) is not int:
        raise MCPInputError("INVALID_ARGUMENT", f"{name} must be an integer")
    num = val
    if num < 0:
        raise MCPInputError("INVALID_ARGUMENT", f"{name} must be non-negative")
    return num


def _as_str(args: dict, name: str, default: str = "",
            *, required: bool = False) -> str:
    if name not in args:
        if required:
            raise MCPInputError("INVALID_ARGUMENT", f"{name} is required")
        return default
    val = args[name]
    if type(val) is str:
        return val
    raise MCPInputError("INVALID_ARGUMENT", f"{name} must be a string")


def _request_binding(args: dict) -> dict:
    goal = _as_str(args, "goal", required=True)
    backend = _as_str(args, "backend", "auto") or "auto"
    model = _as_str(args, "model", "")
    root = _as_str(args, "root", ".") or "."
    check = _as_str(args, "check", "")
    test_cmd = _as_str(args, "test_cmd", "")
    requested_allow_write = _as_bool(args, "allow_write")
    requested_allow_exec = _as_bool(args, "allow_exec")
    gate = ToolGate(allow_write=requested_allow_write,
                    allow_exec=requested_allow_exec)
    binding = {
        "schema": "relay.mcp-run-request/v1",
        "goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
        "root": root,
        "backend": backend,
        "model": model,
        "allow_write": gate.allow_write,
        "allow_exec": gate.allow_exec,
        "requested_allow_write": requested_allow_write,
        "requested_allow_exec": requested_allow_exec,
        "online": _as_bool(args, "online"),
        "max_steps": _as_int(args, "max_steps", 6),
        "max_tokens": _as_int(args, "max_tokens", 512),
        "compact_budget": _as_int(args, "compact_budget", 0),
        "check_present": bool(check),
        "test_cmd_present": bool(test_cmd),
    }
    if check:
        binding["check_sha256"] = hashlib.sha256(check.encode("utf-8")).hexdigest()
    if test_cmd:
        binding["test_cmd_sha256"] = hashlib.sha256(test_cmd.encode("utf-8")).hexdigest()
    return binding


def _backends(args: dict) -> list:
    bs = available_backends(model=_as_str(args, "model", ""))
    if _as_bool(args, "online"):
        from .endpoints import build_endpoints
        bs = bs + build_endpoints()
    return bs


def _agent(args: dict, request_binding: dict | None = None) -> LocalAgent:
    binding = request_binding or {
        "backend": _as_str(args, "backend", "auto") or "auto",
        "max_tokens": _as_int(args, "max_tokens", 512),
    }
    bs = _backends(args)
    prefer = binding["backend"]
    if prefer != "auto" and prefer not in {getattr(b, "name", "") for b in bs}:
        raise MCPInputError("UNSUPPORTED_BACKEND", f"unsupported backend {prefer!r}",
                            request_binding=binding)
    return LocalAgent(backends=bs, prefer=prefer, max_tokens=binding["max_tokens"])


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def _typed_error(err: MCPInputError) -> dict:
    body = {"error": {"code": err.code, "message": str(err)}}
    if err.request_binding is not None:
        body["request_binding"] = err.request_binding
    return {**_text(body), "isError": True}


def _executor(args: dict, request_binding: dict | None = None) -> ToolExecutor:
    binding = request_binding or _request_binding(args)
    return ToolExecutor(root=binding["root"],
                        gate=ToolGate(allow_write=binding["allow_write"],
                                      allow_exec=binding["allow_exec"]))


def _run_kwargs(args: dict, binding: dict) -> dict:
    kwargs = {"max_steps": binding["max_steps"]}
    check = _as_str(args, "check", "")
    test_cmd = _as_str(args, "test_cmd", "")
    if check:
        kwargs["check"] = check
    if test_cmd:
        kwargs["test_cmd"] = test_cmd
    if "compact_budget" in args:
        kwargs["compact_budget"] = binding["compact_budget"]
    return kwargs


def _observed_route(r: dict) -> dict:
    ledger = r.get("ledger")
    entries = getattr(ledger, "entries", [])
    for entry in reversed(entries):
        if getattr(entry, "kind", None) != "assistant":
            continue
        meta = getattr(entry, "meta", {}) or {}
        receipt = meta.get("receipt") if isinstance(meta, dict) else {}
        if not isinstance(receipt, dict):
            receipt = {}
        return {
            "backend": meta.get("backend"),
            "model_ref": receipt.get("model_ref"),
            "receipt_id": receipt.get("receipt_id"),
            "source": "last_witnessed_assistant",
            "seq": getattr(entry, "seq", None),
        }
    return {"backend": None, "model_ref": None, "receipt_id": None,
            "source": "no_witnessed_assistant", "seq": None}


def _run_projection(r: dict, request_binding: dict | None = None) -> dict:
    # verified is the honest composite (chain + re-derivable receipts + a real final
    # answer), never the self-confirming in-memory chain check alone.
    out = {"final": r["final"], "steps": r["steps"], "verified": r["verified"],
           "final_answer": r["final_answer"], "chain_ok": r["chain_ok"],
           "checkpoint": r["checkpoint"],
           "accepted": r.get("accepted"),
           "check_passed": r.get("check_passed"),
           "observed_route": _observed_route(r),
           # the intent/scope audit (claimed_history + any declared drift/scope).
           "intent_audit": r.get("intent_audit", {"findings": [], "critical": 0, "warnings": 0})}
    if "note" in r:
        out["note"] = r["note"]
    if request_binding is not None:
        out["request_binding"] = request_binding
    return out


def _call(params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments", {}) or {}
    try:
        if name == "local_agent_health":
            return _text(health_report(_backends(args)))
        if name == "local_agent_chat":
            prompt = _as_str(args, "prompt", required=True)
            resp = _agent(args).send(prompt)
            return _text({"text": resp["content"][0]["text"], "backend": resp.get("backend"),
                          "receipt": resp.get("x_receipt", {}).get("receipt_id")})
        if name == "local_agent_run":
            binding = _request_binding(args)
            r = run_agent(_agent(args, binding), args["goal"], _executor(args, binding), SessionLedger(),
                          **_run_kwargs(args, binding))
            return _text(_run_projection(r, binding))
        if name == "local_agent_start":
            binding = _request_binding(args)
            agent, goal, ex = _agent(args, binding), args["goal"], _executor(args, binding)
            kwargs = _run_kwargs(args, binding)
            run_id = RUNS.start(
                lambda ledger: _run_projection(run_agent(agent, goal, ex, ledger, **kwargs), binding),
                request_binding=binding)
            return _text({"run_id": run_id, "state": "running",
                          "request_binding": binding})
        if name == "local_agent_status":
            return _text(RUNS.status(_as_str(args, "run_id", required=True)))
        if name == "local_agent_result":
            return _text(RUNS.result(_as_str(args, "run_id", required=True)))
        if name == "local_agent_runs":
            return _text(RUNS.list(limit=_as_int(args, "limit", 20)))
        if name == "local_agent_sessions":
            from .session_store import get_session, list_sessions
            sdir = os.environ.get("RELAY_SESSION_DIR") or "."
            sid = args.get("session_id")
            return _text(get_session(sdir, sid) if sid else list_sessions(sdir))
        if name in ("relay.status", "relay.doctor"):
            info = {"ok": True, "server": "relay", "version": __version__, "protocol": PROTOCOL}
            if name == "relay.doctor":
                info["local_tiers"] = [type(b).__name__ for b in available_backends()]
                info["tools"] = [t["name"] for t in TOOLS]
                # The phone-facing surface is a separate process, so a client
                # holding this stdio server had no way to ask whether it is on.
                # Values are withheld; see remote_state.
                info["remote"] = remote_state()
            return _text(info)
        return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}], "isError": True}
    except MCPInputError as e:
        return _typed_error(e)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"[error] {type(e).__name__}: {e}"}],
                "isError": True}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def _valid_request_id(value) -> bool:
    return type(value) is str or type(value) is int


def _safe_request_id(req: dict):
    if "id" not in req:
        return None
    rid = req["id"]
    return rid if _valid_request_id(rid) else None


def handle(req: dict):
    if not isinstance(req, dict):
        return _err(None, -32600, "invalid request")
    rid = _safe_request_id(req)
    if "id" in req and not _valid_request_id(req["id"]):
        return _err(None, -32600, "invalid request")
    if req.get("jsonrpc") != "2.0":
        return _err(rid, -32600, "invalid request")
    method = req.get("method")
    if not isinstance(method, str):
        return _err(rid, -32600, "invalid request: method must be a string")
    if "id" not in req:
        return None
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                         "serverInfo": {"name": "local-agent", "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        params = req["params"] if "params" in req else {}
        if not isinstance(params, dict):
            return _err(rid, -32602, "invalid params")
        return _ok(rid, _call(params))
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
            stdout.flush()
            continue
        resp = handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
