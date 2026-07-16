"""local_agent_cli.py — CLI/REPL for the standalone local agent (offline tier).

  python -m relay.local_agent_cli --health          # which local tiers are live?
  python -m relay.local_agent_cli "explain this fn" --file foo.py
  python -m relay.local_agent_cli                    # interactive REPL

Runs entirely on local models (serve.py's trained 14B/32B, or Ollama), with
automatic failover. Prints a per-turn receipt id so even offline turns are
witnessed. No hosted account is touched.
"""
from __future__ import annotations

import argparse
import json
import sys

from .local_agent import (
    BackendError,
    LocalAgent,
    available_backends,
    health_report,
)
from .local_git import commit_run
from .local_loop import run_agent, witnessed_edit_paths
from .local_session import SessionLedger
from .local_tools import ToolExecutor, ToolGate


def _all_backends(args) -> list:
    """Local backends, plus the online provider ladder when --online is set."""
    backends = available_backends(serve_url=args.serve_url, ollama_url=args.ollama_url,
                                  model=args.model)
    if getattr(args, "online", False):
        from .endpoints import build_endpoints
        provs = [p.strip() for p in args.providers.split(",")] if args.providers else None
        backends = backends + build_endpoints(providers=provs)
    return backends


def _build_agent(args) -> LocalAgent:
    agent = LocalAgent(backends=_all_backends(args), prefer=args.backend,
                       max_tokens=args.max_tokens, temperature=args.temperature, seed=args.seed)
    if args.system:
        agent.system = args.system
    return agent


def _context_preamble(paths: list[str]) -> str:
    blocks = []
    for p in paths or []:
        try:
            with open(p, encoding="utf-8") as f:
                blocks.append(f"--- FILE: {p} ---\n{f.read()}")
        except OSError as e:
            blocks.append(f"--- FILE: {p} (unreadable: {e}) ---")
    return ("\n\n".join(blocks) + "\n\n") if blocks else ""


def _emit(resp: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(resp, indent=2))
        return
    text = resp["content"][0]["text"] if resp.get("content") else ""
    rid = resp.get("x_receipt", {}).get("receipt_id", "?")
    print(text)
    print(f"\n[{resp.get('backend', '?')} | receipt {rid}]", file=sys.stderr)


def _repl(agent: LocalAgent, as_json: bool) -> int:
    live = agent.live_backend()
    print(f"local-agent REPL — backend: {live.name if live else 'NONE LIVE'} "
          f"(/health, /reset, /exit)", file=sys.stderr)
    while True:
        try:
            line = input("» ").strip()
        except (EOFError, KeyboardInterrupt):
            print(file=sys.stderr)
            return 0
        if not line:
            continue
        if line == "/exit":
            return 0
        if line == "/health":
            print(json.dumps(health_report(agent.backends), indent=2), file=sys.stderr)
            continue
        if line == "/reset":
            agent.history.clear()
            print("(history cleared)", file=sys.stderr)
            continue
        try:
            _emit(agent.send(line), as_json)
        except BackendError as e:
            print(f"[error] {e}", file=sys.stderr)


def _run_agentic(args) -> int:
    if not args.prompt:
        print("[error] --agent needs a task prompt", file=sys.stderr)
        return 2
    agent = _build_agent(args)
    if agent.live_backend() is None:
        print("[error] no local backend is healthy (start serve.py or ollama)", file=sys.stderr)
        return 1
    executor = ToolExecutor(root=args.root,
                            gate=ToolGate(allow_write=args.allow_write, allow_exec=args.allow_exec))
    ledger = SessionLedger()
    result = run_agent(agent, _context_preamble(args.file) + args.prompt, executor, ledger,
                       max_steps=args.max_steps, check=args.check or None)
    print(result["final"])
    if args.save:
        ledger.save(args.save)
    committed = ""
    if args.auto_commit:
        if result["accepted"]:
            # stage only the files the ledger witnessed as edits, so the commit binds
            # the trajectory rather than any other change in the working tree. Only an
            # ACCEPTED run is committed: a failed check, an unfinished run (max_steps),
            # or a backend death all leave the tree uncommitted on the operator's behalf.
            c = commit_run(args.root, args.prompt, result["checkpoint"],
                           paths=witnessed_edit_paths(ledger))
            committed = (f" | committed {c['sha']}" if c.get("committed")
                         else f" | not committed ({c.get('reason')})")
        else:
            committed = " | not committed (run not accepted)"
    chk = "" if result["check_passed"] is None else f" | check={'pass' if result['check_passed'] else 'FAIL'}"
    print(f"\n[agent | {result['steps']} step(s) | {result['entries']} ledger entries | "
          f"verified={result['verified']} | accepted={result['accepted']}{chk} | "
          f"checkpoint {result['checkpoint'][:16]}"
          f"{' | saved ' + args.save if args.save else ''}{committed}]", file=sys.stderr)
    # exit 0 iff the run was ACCEPTED (finished, verified, and any requested check
    # passed), so --agent is a sound CI gate: an unfinished run or one whose check
    # never ran is never reported as success.
    return 0 if result["accepted"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="relay", description=__doc__)
    ap.add_argument("prompt", nargs="?", help="one-shot prompt; omit for a REPL")
    ap.add_argument("--health", action="store_true", help="report live local tiers and exit")
    ap.add_argument("--backend", default="auto",
                    help="force a backend by name (auto|serve|ollama|<provider-mode>)")
    ap.add_argument("--model", default="", help="force an Ollama model name")
    ap.add_argument("--file", action="append", default=[], help="inject a file as context (repeatable)")
    ap.add_argument("--system", default="", help="override the system prompt")
    ap.add_argument("--max-tokens", type=int, default=512, dest="max_tokens")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--serve-url", default="http://127.0.0.1:8765", dest="serve_url")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434", dest="ollama_url")
    ap.add_argument("--json", action="store_true", help="print the full response dict")
    # agentic mode
    ap.add_argument("--agent", action="store_true",
                    help="run the prompt as an agentic task with gated tools + a witnessed ledger")
    ap.add_argument("--root", default=".", help="root for file tools read/list/write (--agent); "
                    "note run/exec sets only cwd and is NOT confined to root")
    ap.add_argument("--allow-write", action="store_true", dest="allow_write")
    ap.add_argument("--allow-exec", action="store_true", dest="allow_exec",
                    help="enable the run tool; a shell can write, so this implies --allow-write "
                    "and is not path-confined")
    ap.add_argument("--max-steps", type=int, default=6, dest="max_steps")
    ap.add_argument("--check", default="",
                    help="an acceptance command (e.g. \"pytest -q\") run once after the "
                    "agent finishes; the run is accepted only if it passes, --auto-commit "
                    "is skipped on failure, and the exit code is non-zero. Witnessed on the "
                    "ledger. Carries operator authority: runs outside the model's tool gate.")
    ap.add_argument("--save", default="", help="save the session ledger to this JSONL path")
    ap.add_argument("--auto-commit", action="store_true", dest="auto_commit",
                    help="git-commit the changes after an --agent run (existing repo only)")
    ap.add_argument("--stream", action="store_true", help="stream tokens as they arrive (one-shot)")
    ap.add_argument("--online", action="store_true",
                    help="add the online provider ladder (codex/claude/gemini/deepseek)")
    ap.add_argument("--providers", default="",
                    help="comma list to restrict online providers (default: all configured)")
    ap.add_argument("--mcp", action="store_true", help="run as a stdio MCP server")
    ap.add_argument("--probe-injection", action="store_true", dest="probe_injection",
                    help="run the defensive prompt-injection robustness probe over the gated tool "
                         "loop and report containment (honors --allow-write/--allow-exec; runs in a "
                         "disposable sandbox, so it never touches the working tree)")
    args = ap.parse_args(argv)

    if args.probe_injection:
        from .injection_probe import probe
        report = probe(allow_write=args.allow_write, allow_exec=args.allow_exec)
        print(json.dumps(report, indent=2))
        return 0 if report["contained"] == report["total"] else 1
    if args.mcp:
        from .local_mcp import serve
        return serve()
    if args.agent:
        return _run_agentic(args)
    if args.health:
        report = health_report(_all_backends(args))
        print(json.dumps(report, indent=2))
        return 0 if report["any_live"] else 1

    agent = _build_agent(args)
    if args.prompt is None:
        return _repl(agent, args.json)
    prompt = _context_preamble(args.file) + args.prompt
    try:
        if args.stream and not args.json:
            resp = agent.stream(prompt, lambda p: (sys.stdout.write(p), sys.stdout.flush()))
            print()
            rid = resp.get("x_receipt", {}).get("receipt_id", "?")
            print(f"[{resp.get('backend', '?')} | receipt {rid}]", file=sys.stderr)
        else:
            _emit(agent.send(prompt), args.json)
    except BackendError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
