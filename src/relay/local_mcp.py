"""local_mcp.py — expose the local/multi-endpoint agent as an MCP server.

So any harness (Claude Code included) can call this agent as a tool: check which
tiers are live, get a one-shot completion, or run a gated agentic task with a
witnessed ledger. Zero-dep stdio JSON-RPC 2.0, the shape every flagship speaks.
`handle()` is transport-free and testable; `serve()` is the thin stdio loop.
"""
from __future__ import annotations

import json
import sys

from .async_runs import RunRegistry
from .local_agent import LocalAgent, available_backends, health_report
from .local_loop import run_agent
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate

PROTOCOL = "2025-06-18"
__version__ = "0.1.0"

# Background runs, so a phone can start a long agentic task and poll it instead of
# holding one blocking HTTP request open across a flaky mobile network.
RUNS = RunRegistry()

_ONLINE = {"online": {"type": "boolean", "description": "include codex/claude/gemini/deepseek"}}
_RUN_ID = {"type": "object", "required": ["run_id"], "properties": {"run_id": {"type": "string"}}}
_RUN_ARGS = {"type": "object", "required": ["goal"],
             "properties": {"goal": {"type": "string"}, "root": {"type": "string"},
                            "allow_write": {"type": "boolean"}, "allow_exec": {"type": "boolean"},
                            "max_steps": {"type": "integer"}, **_ONLINE}}

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
     "description": "Start a gated agentic task in the BACKGROUND and return a run_id at once (does not block). Same gate as local_agent_run (write/exec off unless allowed). Poll local_agent_status for live progress, then local_agent_result for the verified final answer. Use this from a phone or over a flaky network, where a blocking run would drop.",
     "inputSchema": _RUN_ARGS},
    {"name": "local_agent_status",
     "description": "Progress of a background run: state (running/done/error), the step count so far, and the latest witnessed ledger entries.",
     "inputSchema": _RUN_ID},
    {"name": "local_agent_result",
     "description": "The verified final answer and ledger checkpoint of a background run once it is done; reports 'running' until then.",
     "inputSchema": _RUN_ID},
    {"name": "relay.status",
     "description": "Liveness and identity of the relay MCP server (name, version, protocol). Network-free, for a fast health probe.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "relay.doctor",
     "description": "Readiness diagnostic: identity plus the local model tiers configured (serve, ollama) and the tools exposed. Network-free; use local_agent_health to actually ping tiers.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _backends(args: dict) -> list:
    bs = available_backends()
    if args.get("online"):
        from .endpoints import build_endpoints
        bs = bs + build_endpoints()
    return bs


def _agent(args: dict) -> LocalAgent:
    return LocalAgent(backends=_backends(args), prefer=args.get("backend", "auto"),
                      max_tokens=int(args.get("max_tokens", 512)))


def _text(obj) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(obj, indent=2)}]}


def _executor(args: dict) -> ToolExecutor:
    return ToolExecutor(root=args.get("root", "."),
                        gate=ToolGate(allow_write=bool(args.get("allow_write")),
                                      allow_exec=bool(args.get("allow_exec"))))


def _run_projection(r: dict) -> dict:
    # verified is the honest composite (chain + re-derivable receipts + a real final
    # answer), never the self-confirming in-memory chain check alone.
    return {"final": r["final"], "steps": r["steps"], "verified": r["verified"],
            "final_answer": r["final_answer"], "chain_ok": r["chain_ok"],
            "checkpoint": r["checkpoint"]}


def _call(params: dict) -> dict:
    name, args = params.get("name"), params.get("arguments", {}) or {}
    try:
        if name == "local_agent_health":
            return _text(health_report(_backends(args)))
        if name == "local_agent_chat":
            resp = _agent(args).send(args["prompt"])
            return _text({"text": resp["content"][0]["text"], "backend": resp.get("backend"),
                          "receipt": resp.get("x_receipt", {}).get("receipt_id")})
        if name == "local_agent_run":
            r = run_agent(_agent(args), args["goal"], _executor(args), SessionLedger(),
                          max_steps=int(args.get("max_steps", 6)))
            return _text(_run_projection(r))
        if name == "local_agent_start":
            agent, goal, ex = _agent(args), args["goal"], _executor(args)
            steps = int(args.get("max_steps", 6))
            run_id = RUNS.start(
                lambda ledger: _run_projection(run_agent(agent, goal, ex, ledger, max_steps=steps)))
            return _text({"run_id": run_id, "state": "running"})
        if name == "local_agent_status":
            return _text(RUNS.status(args["run_id"]))
        if name == "local_agent_result":
            return _text(RUNS.result(args["run_id"]))
        if name in ("relay.status", "relay.doctor"):
            info = {"ok": True, "server": "relay", "version": __version__, "protocol": PROTOCOL}
            if name == "relay.doctor":
                info["local_tiers"] = [type(b).__name__ for b in available_backends()]
                info["tools"] = [t["name"] for t in TOOLS]
            return _text(info)
        return {"content": [{"type": "text", "text": f"unknown tool {name!r}"}], "isError": True}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"[error] {type(e).__name__}: {e}"}],
                "isError": True}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def handle(req: dict):
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        return _ok(rid, {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                         "serverInfo": {"name": "local-agent", "version": __version__}})
    if method == "tools/list":
        return _ok(rid, {"tools": TOOLS})
    if method == "tools/call":
        return _ok(rid, _call(req.get("params", {})))
    if rid is None:
        return None
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
            continue
        resp = handle(req)
        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(serve())
