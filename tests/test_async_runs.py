"""Falsifiers for the background-run registry (async_runs.RunRegistry).

A phone starts a long agent run and polls it: start must return at once, status
must show live progress before completion, result must gate until done, a raising
work must be captured (never a lost traceback), and the registry must stay
bounded.
"""
import threading
import time

from relay.async_runs import DONE, ERROR, RUNNING, RunRegistry


def _wait(reg, run_id, want, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if reg.status(run_id).get("state") == want:
            return True
        time.sleep(0.005)
    return False


def test_start_returns_id_at_once_then_completes():
    reg = RunRegistry(id_source=lambda: "run-1", clock=lambda: 42)

    def work(ledger):
        ledger.append("assistant", "did the thing")
        return {"final": "ok"}

    run_id = reg.start(work)
    assert run_id == "run-1"
    assert _wait(reg, run_id, DONE)
    res = reg.result(run_id)
    assert res["state"] == DONE and res["result"] == {"final": "ok"}
    assert reg.status(run_id)["started"] == 42


def test_status_shows_live_progress_before_completion():
    reg = RunRegistry()
    started, release = threading.Event(), threading.Event()

    def work(ledger):
        ledger.append("assistant", "step one")
        started.set()
        release.wait(3.0)  # hold the run open so the test observes it running
        ledger.append("assistant", "step two")
        return {"final": "done"}

    run_id = reg.start(work)
    assert started.wait(3.0)
    mid = reg.status(run_id)
    assert mid["state"] == RUNNING and mid["steps"] >= 1
    assert mid["latest"] and mid["latest"][-1]["kind"] == "assistant"
    assert reg.result(run_id)["state"] == RUNNING  # not ready while running
    release.set()
    assert _wait(reg, run_id, DONE)
    assert reg.status(run_id)["steps"] == 2


def test_error_in_work_is_captured_not_raised():
    reg = RunRegistry()

    def work(ledger):
        raise RuntimeError("every backend died")

    run_id = reg.start(work)
    assert _wait(reg, run_id, ERROR)
    res = reg.result(run_id)
    assert res["state"] == ERROR and "every backend died" in res["error"]


def test_unknown_run_id_is_typed_not_a_crash():
    reg = RunRegistry()
    assert "error" in reg.status("nope")
    assert "error" in reg.result("nope")


def test_registry_evicts_the_oldest_beyond_max():
    reg = RunRegistry(max_runs=2)

    def work(ledger):
        return {"ok": True}

    ids = [reg.start(work) for _ in range(3)]
    # the third start pushes the registry over the cap; the oldest record is gone
    assert "error" in reg.status(ids[0])
    assert _wait(reg, ids[2], DONE)
