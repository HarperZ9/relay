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

import json
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from .local_session import Entry, SessionLedger

RUNNING = "running"
DONE = "done"
ERROR = "error"
INTERRUPTED = "interrupted"   # a run whose worker was lost to a restart


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
                 id_source: Callable[[], str] = _hex_id, max_runs: int = 64,
                 run_root: "str | None" = None) -> None:
        self._runs: OrderedDict[str, _Run] = OrderedDict()
        self._lock = threading.Lock()
        self._clock = clock
        self._id_source = id_source
        self._max_runs = max_runs
        # With a run_root, records persist so a phone's run_id survives a restart:
        # a finished run is fetchable again, and a run cut off mid-flight is honestly
        # reloaded as INTERRUPTED with whatever it had witnessed.
        self._run_root = run_root
        if run_root:
            os.makedirs(run_root, exist_ok=True)
            self._load_all()

    def _path(self, run_id: str) -> str:
        return os.path.join(self._run_root, f"{run_id}.json")

    def _persist(self, run: _Run) -> None:
        if not self._run_root:
            return
        rec = {"run_id": run.run_id, "state": run.state, "result": run.result,
               "error": run.error, "started": run.started, "finished": run.finished,
               "ledger_jsonl": run.ledger.to_jsonl()}
        tmp = self._path(run.run_id) + ".tmp"
        for _ in range(6):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(rec, f)
                os.replace(tmp, self._path(run.run_id))   # atomic swap
                return
            except OSError:
                # a transient lock (a racing reader on Windows) is retried; persistence
                # stays best-effort and never breaks the run if the disk is unavailable.
                time.sleep(0.02)

    def _load_all(self) -> None:
        loaded: list[_Run] = []
        for name in sorted(os.listdir(self._run_root)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(self._run_root, name), encoding="utf-8") as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            led = SessionLedger()
            for line in (rec.get("ledger_jsonl") or "").splitlines():
                if line.strip():
                    led.entries.append(Entry(**json.loads(line)))
            state = rec.get("state")
            if state == RUNNING:               # the worker that ran it is gone
                state = INTERRUPTED
            loaded.append(_Run(rec.get("run_id", name[:-5]), led, state=state,
                               result=rec.get("result"), error=rec.get("error"),
                               started=rec.get("started", 0), finished=rec.get("finished")))
        loaded.sort(key=lambda r: r.started)   # oldest first, so eviction keeps the newest
        with self._lock:
            for r in loaded[-self._max_runs:]:
                self._runs[r.run_id] = r

    def start(self, work: Callable[[SessionLedger], dict]) -> str:
        """Run ``work(ledger)`` in a daemon thread; return its run_id at once.
        ``work`` receives the run's ledger, so its progress is observable live and
        its return value becomes the result."""
        run_id = self._id_source()
        run = _Run(run_id, SessionLedger(), started=self._clock())
        with self._lock:
            self._runs[run_id] = run
            while len(self._runs) > self._max_runs:
                old_id, _ = self._runs.popitem(last=False)  # evict the oldest record
                if self._run_root:
                    try:
                        os.remove(self._path(old_id))
                    except OSError:
                        pass
        self._persist(run)
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
            self._persist(run)   # the finished run survives a restart, fetchable again

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
        if run.state == INTERRUPTED:
            return {"run_id": run_id, "state": INTERRUPTED,
                    "note": "interrupted by a restart; the witnessed ledger is partial"}
        return {"run_id": run_id, "state": DONE, "result": run.result}

    def list(self, *, limit: int = 20) -> dict:
        """Recent runs, newest first, so a phone that lost its run_id can find it
        again after a restart. Each row carries state, timing, and the step count."""
        with self._lock:
            runs = list(self._runs.values())
        runs.sort(key=lambda r: r.started, reverse=True)
        rows = [{"run_id": r.run_id, "state": r.state, "started": r.started,
                 "finished": r.finished,
                 "steps": sum(1 for e in r.ledger.entries if e.kind == "assistant")}
                for r in runs[:limit]]
        return {"runs": rows, "count": len(rows)}
