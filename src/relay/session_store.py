"""session_store.py -- list and open saved relay sessions, so a session follows you.

A relay run saves its witnessed ledger to a JSONL file (SessionLedger.save). This
lists the ledgers in a directory as sessions the same user on another device can
reopen, and hands back one session's transcript. Each is re-verified, so a tampered
saved session reads as unverified here instead of being trusted silently, and
run_agent resumes from a loaded ledger by continuing its hash chain. Pure over a
directory of ledger files; zero dependencies.
"""
from __future__ import annotations

import os

from .local_session import SessionLedger


def _first_goal(ledger) -> str:
    for e in ledger.entries:
        if e.kind == "user":
            return e.content[:200]
    return ""


def session_summary(ledger, session_id: str) -> dict:
    return {
        "id": session_id,
        "goal": _first_goal(ledger),
        "entries": len(ledger.entries),
        "checkpoint": ledger.checkpoint(),
        "verified": ledger.verify(),   # a tampered saved session reads False, not hidden
    }


def list_sessions(directory: str) -> dict:
    """Every saved ledger in `directory` as a reopenable session, newest file first.
    A file that will not parse is skipped rather than crashing the listing."""
    if not os.path.isdir(directory):
        return {"sessions": [], "count": 0}
    names = [n for n in os.listdir(directory) if n.endswith(".jsonl")]
    names.sort(key=lambda n: os.path.getmtime(os.path.join(directory, n)), reverse=True)
    rows = []
    for name in names:
        try:
            led = SessionLedger.load(os.path.join(directory, name), verify=False)
        except (OSError, ValueError):
            continue
        rows.append(session_summary(led, name[:-6]))
    return {"sessions": rows, "count": len(rows)}


def get_session(directory: str, session_id: str) -> dict:
    """One session's transcript plus its verification, or an error if it is missing
    or unreadable. Loads without raising so a tampered file is reported, not trusted."""
    path = os.path.join(directory, f"{session_id}.jsonl")
    if not os.path.isfile(path):
        return {"error": f"unknown session {session_id!r}"}
    try:
        led = SessionLedger.load(path, verify=False)
    except (OSError, ValueError) as e:
        return {"error": f"cannot read session {session_id!r}: {type(e).__name__}"}
    return {**session_summary(led, session_id), "transcript": led.transcript()}
