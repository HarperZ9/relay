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


# --- durability: a run_id survives a restart when a run_root is set ---

import json  # noqa: E402


def test_a_finished_run_survives_a_restart(tmp_path):
    root = str(tmp_path / "runs")
    reg = RunRegistry(id_source=lambda: "run-keep", run_root=root)

    def work(ledger):
        ledger.append("assistant", "did it")
        return {"final": "kept"}

    run_id = reg.start(work)
    assert _wait(reg, run_id, DONE)

    # a restarted process (a fresh registry on the same root) must see the run again;
    # poll because persistence lands a hair after the in-memory DONE transition.
    end = time.time() + 3.0
    while time.time() < end and RunRegistry(run_root=root).result(run_id)["state"] != DONE:
        time.sleep(0.02)
    reborn = RunRegistry(run_root=root)
    res = reborn.result(run_id)
    assert res["state"] == DONE and res["result"] == {"final": "kept"}
    assert reborn.status(run_id)["steps"] == 1   # the witnessed ledger survived too


def test_list_returns_recent_runs_newest_first(tmp_path):
    clock = [1]
    reg = RunRegistry(run_root=str(tmp_path / "runs"), clock=lambda: clock[0])

    def work(ledger):
        return {"ok": True}

    a = reg.start(work)
    clock[0] = 2
    b = reg.start(work)
    assert _wait(reg, a, DONE) and _wait(reg, b, DONE)
    listing = reg.list()
    ids = [r["run_id"] for r in listing["runs"]]
    assert ids[0] == b and a in ids          # newest first
    assert listing["count"] == 2


def test_a_run_cut_off_mid_flight_reloads_as_interrupted(tmp_path):
    from relay.async_runs import INTERRUPTED
    root = tmp_path / "runs"
    root.mkdir()
    (root / "run-x.json").write_text(json.dumps({
        "run_id": "run-x", "state": "running", "result": None, "error": None,
        "started": 5, "finished": None, "ledger_jsonl": ""}), encoding="utf-8")
    reg = RunRegistry(run_root=str(root))
    assert reg.result("run-x")["state"] == INTERRUPTED
    assert reg.list()["runs"][0]["state"] == INTERRUPTED


def test_persistence_is_off_without_a_run_root():
    reg = RunRegistry()

    def work(ledger):
        return {"ok": True}

    rid = reg.start(work)
    assert _wait(reg, rid, DONE)
    assert "error" in RunRegistry().result(rid)   # a fresh registry shares nothing
