"""async_runs.py — start a gated agent run in the background, poll its progress.

A blocking HTTP POST that runs a multi-step agent is fine on localhost but drops
on a mobile network long before a real coding run finishes, and a phone MCP
connector times the call out. This registry starts the work in a background
thread against a fresh witnessed ledger and hands back a run_id at once. A phone
then polls status (steps so far + the latest witnessed ledger entries) and
fetches the result (the verified checkpoint) when the run is done -- each poll a
short request that survives a dropped connection.

Determinism is by injection (clock + id source), so the registry is testable
without wall-clock time or real randomness. The registry is bounded and evicts
the oldest run records; a still-running loop is bounded by its own max_steps.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from .local_session import SessionLedger

RUNNING = "running"
DONE = "done"
ERROR = "error"


@dataclass
class _Run:
    run_id: str
    ledger: SessionLedger
    state: str = RUNNING
    result: dict | None = None
    error: str | None = None
    started: int = 0
    finished: int | None = None


def _now() -> int:
    return int(time.time())


def _hex_id() -> str:
    return os.urandom(8).hex()


class RunRegistry:
    """Thread-safe registry of background agent runs; bounded and self-evicting."""

    def __init__(self, *, clock: Callable[[], int] = _now,
                 id_source: Callable[[], str] = _hex_id, max_runs: int = 64) -> None:
        self._runs: OrderedDict[str, _Run] = OrderedDict()
        self._lock = threading.Lock()
        self._clock = clock
        self._id_source = id_source
        self._max_runs = max_runs

    def start(self, work: Callable[[SessionLedger], dict]) -> str:
        """Run ``work(ledger)`` in a daemon thread; return its run_id at once.
        ``work`` receives the run's ledger, so its progress is observable live and
        its return value becomes the result."""
        run_id = self._id_source()
        run = _Run(run_id, SessionLedger(), started=self._clock())
        with self._lock:
            self._runs[run_id] = run
            while len(self._runs) > self._max_runs:
                self._runs.popitem(last=False)  # evict the oldest record
        threading.Thread(target=self._execute, args=(run, work), daemon=True).start()
        return run_id

    def _execute(self, run: _Run, work: Callable[[SessionLedger], dict]) -> None:
        try:
            result = work(run.ledger)
            with self._lock:
                run.result, run.state = result, DONE
        except Exception as exc:  # a dead backend or a raising tool is witnessed, not lost
            with self._lock:
                run.error, run.state = f"{type(exc).__name__}: {exc}", ERROR
        finally:
            with self._lock:
                run.finished = self._clock()

    def _get(self, run_id: str) -> _Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def status(self, run_id: str, *, tail: int = 5) -> dict:
        """State, step count, and the last few witnessed ledger entries. Reading a
        prefix of an append-only list is safe against the worker's appends."""
        run = self._get(run_id)
        if run is None:
            return {"error": f"unknown run_id {run_id!r}"}
        entries = run.ledger.entries
        latest = [{"seq": e.seq, "kind": e.kind, "summary": e.content[:160]}
                  for e in entries[-tail:]]
        out = {"run_id": run_id, "state": run.state,
               "steps": sum(1 for e in entries if e.kind == "assistant"),
               "entries": len(entries), "latest": latest,
               "started": run.started, "finished": run.finished}
        if run.state == ERROR:
            out["error"] = run.error
        return out

    def result(self, run_id: str) -> dict:
        """The work's return value once the run is done; 'running' until then."""
        run = self._get(run_id)
        if run is None:
            return {"error": f"unknown run_id {run_id!r}"}
        if run.state == RUNNING:
            return {"run_id": run_id, "state": RUNNING,
                    "note": "still running; poll local_agent_status"}
        if run.state == ERROR:
            return {"run_id": run_id, "state": ERROR, "error": run.error}
        return {"run_id": run_id, "state": DONE, "result": run.result}
