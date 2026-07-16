"""local_loop.py — the agentic loop: local model + gated tools + witnessed ledger.

This is what turns the chat client into an actual local coding agent. The model
proposes tool calls in the text protocol, the executor runs them under the gate,
observations are fed back, and the whole trajectory (turns + tool calls +
results) is appended to a hash-chained SessionLedger. The loop terminates when
the model stops emitting TOOL lines (final answer) or max_steps is hit — always
returning a re-verifiable checkpoint, and recording a backend death mid-run as an
honest error entry rather than an uncaught traceback.
"""
from __future__ import annotations

import json
import subprocess

from .local_agent import BackendError
from .local_session import SessionLedger
from .local_tools import TOOLS_SYSTEM, ToolExecutor, parse_tool_calls
from .messages_api import recompute_receipt_id

_CHECK_TIMEOUT = 600   # an acceptance check (a test/build suite) may be slow


def run_agent(agent, goal: str, executor: ToolExecutor,
              ledger: "SessionLedger | None" = None, *, max_steps: int = 6,
              check: "str | None" = None) -> dict:
    """Run the goal to completion (or max_steps). Returns the final answer, the
    step count, and the ledger checkpoint + verdict.

    ``check`` is an optional operator-supplied acceptance command (e.g. ``pytest -q``).
    When the agent produces a final answer it is run once, its result is witnessed on
    the ledger, and the run is ACCEPTED only if it passes. The check carries operator
    authority (the operator chose it), so it runs outside the model's tool gate; it is
    never a call the model can emit or steer."""
    ledger = ledger if ledger is not None else SessionLedger()
    if TOOLS_SYSTEM not in agent.system:
        agent.system = agent.system + "\n\n" + TOOLS_SYSTEM

    ledger.append("user", goal)
    message = goal
    for step in range(1, max_steps + 1):
        try:
            resp = agent.send(message)
        except BackendError as e:
            # every backend died mid-run: witness the failure (with the partial
            # work already on the chain) instead of letting it vanish as a traceback.
            ledger.append("error", str(e), {"step": step})
            return _done(f"[backend failure at step {step}] {e}", step, ledger,
                         final_answer=False)
        text = resp["content"][0]["text"] if resp.get("content") else ""
        meta = {"backend": resp.get("backend"),
                "receipt": resp.get("x_receipt", {})}   # the FULL receipt, re-derivable
        if resp.get("failover"):
            meta["failover"] = resp["failover"]         # a failed earlier tier is bound in
        ledger.append("assistant", text, meta)

        calls = parse_tool_calls(text)
        if not calls:
            return _done(text, step, ledger, final_answer=True,
                         check_passed=_run_acceptance(check, executor, ledger))

        observations = []
        for name, args in calls:
            res = executor.execute(name, args)
            ledger.append("tool_call", f"{name} {json.dumps(args, sort_keys=True)}")
            ledger.append("tool_result", res.output, {"tool": name, "ok": res.ok})
            observations.append(f"TOOL {name} -> {'ok' if res.ok else 'FAIL'}:\n{res.output}")

        message = ("TOOL RESULTS:\n" + "\n\n".join(observations) +
                   "\n\nContinue if you need more tools, otherwise give the final "
                   "answer with no TOOL line.")
        ledger.append("user", message)   # the continuation prompt the model actually sees next

    return _done("[max_steps reached without a final answer]", max_steps, ledger,
                 final_answer=False)


def _run_acceptance(check: "str | None", executor: ToolExecutor,
                    ledger: SessionLedger) -> "bool | None":
    """Run the operator's acceptance command in the executor's root and witness the
    result on the ledger. Returns True/False, or None when no check was requested.
    A timeout is its own honest failure, not a silent pass."""
    if not check:
        return None
    try:
        if executor.runner is not None:            # injected for tests
            ok, out = executor.runner(check, executor.root)
        else:
            proc = subprocess.run(check, shell=True, cwd=executor.root,
                                  capture_output=True, text=True, timeout=_CHECK_TIMEOUT)
            ok = proc.returncode == 0
            out = f"[exit {proc.returncode}]\n{(proc.stdout or '') + (proc.stderr or '')}"
    except subprocess.TimeoutExpired:
        ok, out = False, f"[check timeout after {_CHECK_TIMEOUT}s]"
    except Exception as e:
        # a check that cannot even run (bad cwd, a raising runner) is a FAILED
        # acceptance, witnessed like any other, never a traceback that discards the
        # checkpoint the loop built.
        ok, out = False, f"[check errored: {type(e).__name__}: {e}]"
    ledger.append("check", str(out)[:4000], {"cmd": check, "ok": bool(ok)})
    return bool(ok)


def _done(final: str, steps: int, ledger: SessionLedger, *, final_answer: bool,
          check_passed: "bool | None" = None) -> dict:
    from .integrity import integrity_report, trajectory_integrity
    chain_ok = ledger.verify()
    receipts_ok = verify_receipts(ledger)
    verified = chain_ok and receipts_ok and final_answer
    integrity = integrity_report(trajectory_integrity(ledger))
    # A passing check is TRUSTED only if the trajectory did not tamper with the thing
    # that grades it (edit the test file, inject a skip/exit). No check ran -> there was
    # nothing to game, so trust is not in question.
    check_trusted = check_passed is not True or integrity["clean"]
    return {"final": final, "steps": steps,
            "checkpoint": ledger.checkpoint(),
            "chain_ok": chain_ok,          # in-memory chain integrity (structural)
            "receipts_ok": receipts_ok,    # every per-turn receipt id re-derives from stored fields
            "final_answer": final_answer,  # a real final answer was produced (not max_steps / failure)
            # honest composite, NOT the self-confirming in-memory check alone: a
            # run only "verifies" if the chain holds, the receipts re-derive, AND an
            # answer was actually produced.
            "verified": verified,
            "check_passed": check_passed,  # the acceptance check's verdict, or None if none was run
            "integrity": integrity,        # reward-hacking flags over the witnessed edit set
            "check_trusted": check_trusted,  # a pass survives only if the grader was not tampered with
            # ACCEPTED = a verified trajectory whose acceptance check did not fail AND
            # whose pass was not gamed by tampering with the check. No check -> collapses
            # to `verified`; a failed OR tampered pass is never accepted.
            "accepted": verified and check_passed is not False and check_trusted,
            "entries": len(ledger.entries), "ledger": ledger}


def verify_receipts(ledger: SessionLedger) -> bool:
    """Re-derive every stored per-turn receipt_id from its own recorded fields.
    Fail-closed: an assistant turn that claims a receipt but lacks the fields to
    re-derive it is NOT accepted — an opaque id no stranger can re-check is
    unverifiable, never a pass."""
    for e in ledger.entries:
        if e.kind != "assistant":
            continue
        rec = e.meta.get("receipt")
        if not rec:
            continue
        if not isinstance(rec, dict) or "receipt_id" not in rec:
            return False
        try:
            if recompute_receipt_id(rec) != rec["receipt_id"]:
                return False
        except (KeyError, TypeError):
            return False
    return True


def witnessed_edit_paths(ledger: SessionLedger) -> list:
    """Paths the ledger recorded as write_file/edit_file targets — the edit set a
    commit is allowed to bind. A file written another way (shell redirection via
    `run`) is not recorded as content here, so it is never attributed to the
    witnessed trajectory."""
    paths: list = []
    for e in ledger.entries:
        if e.kind != "tool_call":
            continue
        name, _, rest = e.content.partition(" ")
        if name not in ("write_file", "edit_file"):
            continue
        try:
            args = json.loads(rest)
        except json.JSONDecodeError:
            continue
        p = args.get("path")
        if p and p not in paths:
            paths.append(p)
    return paths
