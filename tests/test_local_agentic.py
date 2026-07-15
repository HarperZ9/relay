"""Falsifiers for the agentic local agent (tools + gate + witnessed ledger + loop).

These back the 'more than a chat client' claim: (1) tools are sandboxed to a root
and default-deny for write/exec, with a denylist even when exec is allowed;
(2) the session ledger is hash-chained and tamper-evident, and round-trips
through save/load; (3) the agentic loop executes gated tools, feeds observations
back, records the whole trajectory, and returns a re-verifiable checkpoint.
"""
import json

import pytest

from relay.local_agent import BackendError
from relay.local_loop import run_agent, verify_receipts, witnessed_edit_paths
from relay.local_session import SessionLedger
from relay.local_tools import ToolExecutor, ToolGate, parse_tool_calls
from relay.messages_api import make_receipt, recompute_receipt_id


# ── tools + gate + sandbox ────────────────────────────────────────────────

def test_parse_tool_calls_skips_malformed():
    text = ('TOOL read_file {"path": "a"}\n'
            'TOOL bad {not json}\n'
            'just prose, no tool\n'
            'TOOL run {"cmd": "ls"}')
    assert parse_tool_calls(text) == [("read_file", {"path": "a"}),
                                      ("run", {"cmd": "ls"})]


def test_read_and_list_are_sandboxed(tmp_path):
    (tmp_path / "in.txt").write_text("data", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path))
    good = ex.execute("read_file", {"path": "in.txt"})
    assert good.ok and good.output == "data"
    escape = ex.execute("read_file", {"path": "../../../../etc/passwd"})
    assert not escape.ok and "escapes root" in escape.output


def test_exec_gate_and_denylist():
    off = ToolExecutor(root=".", gate=ToolGate(allow_exec=False))
    assert not off.execute("run", {"cmd": "echo hi"}).ok        # exec disabled by default
    on = ToolExecutor(root=".", gate=ToolGate(allow_exec=True),
                      runner=lambda cmd, root: (True, "ran"))
    assert on.execute("run", {"cmd": "echo hi"}).ok             # allowed via injected runner
    blocked = on.execute("run", {"cmd": "rm -rf /"})
    assert not blocked.ok and "denylist" in blocked.output      # destructive blocked even when allowed


def test_exec_implies_write_capability(tmp_path):
    # A shell can write, so --allow-exec cannot honestly keep files immutable. The
    # gate no longer presents writes as 'off' while exec is on: enabling exec
    # enables write, consistently — write_file is allowed, not falsely gated-off,
    # exactly the capability the run tool already grants.
    assert ToolGate(allow_exec=True).allow_write is True
    assert ToolGate(allow_exec=False).allow_write is False       # exec off -> unchanged
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_exec=True))
    w = ex.execute("write_file", {"path": "a.txt", "content": "x"})
    assert w.ok and (tmp_path / "a.txt").read_text() == "x"


def test_write_gate_default_deny_then_allowed(tmp_path):
    denied = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False))
    r = denied.execute("write_file", {"path": "x.txt", "content": "hi"})
    assert not r.ok and not (tmp_path / "x.txt").exists()
    ok = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    w = ok.execute("write_file", {"path": "sub/out.txt", "content": "xyz"})
    assert w.ok and (tmp_path / "sub" / "out.txt").read_text() == "xyz"


def test_unknown_tool_and_tool_exception_are_results_not_crashes(tmp_path):
    ex = ToolExecutor(root=str(tmp_path))
    assert not ex.execute("nope", {}).ok
    assert not ex.execute("read_file", {"path": "missing.txt"}).ok   # exception -> ok=False


def test_edit_file_requires_a_unique_match(tmp_path):
    (tmp_path / "m.py").write_text("a = 1\nb = 1\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=True))
    # unique -> applied
    ok = ex.execute("edit_file", {"path": "m.py", "old": "a = 1", "new": "a = 2"})
    assert ok.ok and (tmp_path / "m.py").read_text() == "a = 2\nb = 1\n"
    # not found -> refused, file untouched
    miss = ex.execute("edit_file", {"path": "m.py", "old": "zzz", "new": "q"})
    assert not miss.ok and "not found" in miss.output
    # ambiguous -> refused (both '= 1' lines), file untouched
    (tmp_path / "d.py").write_text("x = 1\ny = 1\n", encoding="utf-8")
    amb = ex.execute("edit_file", {"path": "d.py", "old": " 1", "new": " 9"})
    assert not amb.ok and "matches 2" in amb.output
    assert (tmp_path / "d.py").read_text() == "x = 1\ny = 1\n"


def test_edit_file_is_gated_like_write(tmp_path):
    (tmp_path / "m.py").write_text("k = 1\n", encoding="utf-8")
    denied = ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False))
    r = denied.execute("edit_file", {"path": "m.py", "old": "k = 1", "new": "k = 2"})
    assert not r.ok and "[gate]" in r.output
    assert (tmp_path / "m.py").read_text() == "k = 1\n"          # unchanged


def test_repo_map_tool_lists_symbols(tmp_path):
    (tmp_path / "mod.py").write_text("class Foo:\n    def bar(self):\n        pass\n"
                                     "def top():\n    pass\n", encoding="utf-8")
    ex = ToolExecutor(root=str(tmp_path))
    r = ex.execute("repo_map", {"path": "."})
    assert r.ok
    assert "class Foo" in r.output and "def bar" in r.output and "def top" in r.output


# ── witnessed session ledger ──────────────────────────────────────────────

def test_ledger_chains_and_tamper_is_detected():
    led = SessionLedger()
    led.append("user", "hi")
    led.append("assistant", "yo")
    assert led.verify()
    led.entries[0].content = "TAMPERED"
    assert led.verify() is False


def test_ledger_save_load_roundtrip(tmp_path):
    led = SessionLedger()
    led.append("user", "q")
    led.append("assistant", "a", {"backend": "ollama"})
    p = tmp_path / "s.jsonl"
    led.save(str(p))
    back = SessionLedger.load(str(p))
    assert back.verify() and back.checkpoint() == led.checkpoint()
    assert back.transcript() == [{"role": "user", "content": "q"},
                                 {"role": "assistant", "content": "a"}]


# ── the agentic loop ──────────────────────────────────────────────────────

class ScriptedAgent:
    """A fake LocalAgent: returns queued replies, records what it was sent. Emits a
    real per-turn receipt (full fields) so the loop's receipt re-derivation is
    exercised, not stubbed away."""

    def __init__(self, replies, backend="stub"):
        self.system = "base system"
        self._replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        text = self._replies.pop(0) if self._replies else "done"
        receipt = make_receipt(
            {"prompt": message, "system": self.system, "max_new_tokens": 512,
             "temperature": 0.0, "seed": 0, "requested_model": "stub"},
            {"text": text, "seed": 0}, "stub")
        return {"content": [{"type": "text", "text": text}], "backend": "stub",
                "x_receipt": receipt}


class FailingAgent:
    """Succeeds for the scripted replies, then every backend fails (BackendError),
    to exercise a mid-loop endpoint death."""

    def __init__(self, replies):
        self.system = "base system"
        self._replies = list(replies)
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        if not self._replies:
            raise BackendError("all healthy backends failed: serve; ollama")
        text = self._replies.pop(0)
        receipt = make_receipt(
            {"prompt": message, "system": self.system, "max_new_tokens": 512,
             "temperature": 0.0, "seed": 0, "requested_model": "stub"},
            {"text": text, "seed": 0}, "stub")
        return {"content": [{"type": "text", "text": text}], "backend": "stub",
                "x_receipt": receipt}


def test_loop_executes_tools_and_witnesses_the_full_trajectory(tmp_path):
    (tmp_path / "a.txt").write_text("hello world", encoding="utf-8")
    agent = ScriptedAgent(['TOOL read_file {"path": "a.txt"}',
                           "the file says hello world"])
    led = SessionLedger()
    res = run_agent(agent, "what does a.txt say?",
                    ToolExecutor(root=str(tmp_path)), led, max_steps=4)
    assert res["final"] == "the file says hello world"
    assert res["steps"] == 2 and res["verified"] is True
    # the continuation prompt the model actually saw is recorded as a user turn too
    assert [e.kind for e in led.entries] == \
        ["user", "assistant", "tool_call", "tool_result", "user", "assistant"]
    cont = led.entries[4]
    assert cont.kind == "user" and "TOOL RESULTS" in cont.content
    tr = next(e for e in led.entries if e.kind == "tool_result")
    assert "hello world" in tr.content


def test_loop_respects_the_gate_and_keeps_going(tmp_path):
    agent = ScriptedAgent(['TOOL write_file {"path": "x.txt", "content": "hi"}',
                           "I was not allowed to write"])
    led = SessionLedger()
    res = run_agent(agent, "write x.txt",
                    ToolExecutor(root=str(tmp_path), gate=ToolGate(allow_write=False)),
                    led, max_steps=3)
    assert not (tmp_path / "x.txt").exists()          # gate held
    assert res["final"] == "I was not allowed to write"
    tr = next(e for e in led.entries if e.kind == "tool_result")
    assert "[gate]" in tr.content


def test_loop_stops_at_max_steps_and_reports_an_honest_verdict(tmp_path):
    # a model that always asks for another tool never "finishes". max_steps
    # exhaustion is NOT a verified run: the chain is intact (chain_ok) but no real
    # final answer was produced, so the composite verdict is honestly False.
    agent = ScriptedAgent(['TOOL list_dir {"path": "."}'] * 10)
    led = SessionLedger()
    res = run_agent(agent, "loop forever",
                    ToolExecutor(root=str(tmp_path)), led, max_steps=3)
    assert res["steps"] == 3 and "max_steps" in res["final"]
    assert res["chain_ok"] is True          # in-memory integrity holds
    assert res["final_answer"] is False     # but no answer was produced
    assert res["verified"] is False         # so the composite is not a vacuous True


def test_tools_system_prompt_is_installed_once():
    from relay.local_tools import TOOLS_SYSTEM
    agent = ScriptedAgent(["done", "done again"])
    run_agent(agent, "hi", ToolExecutor(root="."), SessionLedger(), max_steps=1)
    run_agent(agent, "again", ToolExecutor(root="."), SessionLedger(), max_steps=1)  # resume
    assert TOOLS_SYSTEM in agent.system
    assert agent.system.count(TOOLS_SYSTEM) == 1     # guard prevents re-append


# ── witnessed loop: failures, full receipts, honest verdict ────────────────

def test_mid_loop_backend_failure_is_recorded_not_an_uncaught_raise(tmp_path):
    # 1 good step (a tool call), then every backend dies. The partial work must be
    # witnessed with an error entry + checkpoint, not thrown away as a traceback.
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    agent = FailingAgent(['TOOL read_file {"path": "a.txt"}'])   # then send() raises
    led = SessionLedger()
    res = run_agent(agent, "read it", ToolExecutor(root=str(tmp_path)), led, max_steps=4)
    kinds = [e.kind for e in led.entries]
    assert "error" in kinds                                   # the failure is on the record
    err = next(e for e in led.entries if e.kind == "error")
    assert "backends failed" in err.content
    assert res["final_answer"] is False and res["verified"] is False
    assert res["chain_ok"] is True and res["checkpoint"] == led.checkpoint()


def test_assistant_entries_store_a_re_derivable_receipt(tmp_path):
    agent = ScriptedAgent(["the answer"])
    led = SessionLedger()
    run_agent(agent, "q", ToolExecutor(root=str(tmp_path)), led, max_steps=2)
    a = next(e for e in led.entries if e.kind == "assistant")
    rec = a.meta["receipt"]
    # the FULL receipt is stored (not just an opaque id), so a stranger can re-derive it
    assert {"request_hash", "prompt_hash", "response_hash", "model_ref"} <= set(rec)
    assert recompute_receipt_id(rec) == rec["receipt_id"]


def test_verify_receipts_is_fail_closed_on_a_tampered_receipt(tmp_path):
    agent = ScriptedAgent(["the answer"])
    led = SessionLedger()
    res = run_agent(agent, "q", ToolExecutor(root=str(tmp_path)), led, max_steps=2)
    assert res["receipts_ok"] is True
    # tamper the stored response_hash: the receipt_id no longer re-derives
    a = next(e for e in led.entries if e.kind == "assistant")
    a.meta["receipt"]["response_hash"] = "0" * 16
    assert verify_receipts(led) is False


def test_load_rejects_a_tampered_ledger(tmp_path):
    led = SessionLedger()
    led.append("user", "hi")
    led.append("assistant", "yo")
    p = tmp_path / "s.jsonl"
    led.save(str(p))
    lines = p.read_text(encoding="utf-8").splitlines()
    obj = json.loads(lines[0])
    obj["content"] = "HACKED"                                 # break the chain
    lines[0] = json.dumps(obj)
    p.write_text("\n".join(lines), encoding="utf-8")
    with pytest.raises(ValueError, match="verify"):
        SessionLedger.load(str(p))


def test_witnessed_edit_paths_are_only_the_recorded_write_targets():
    led = SessionLedger()
    led.append("user", "goal")
    led.append("tool_call", 'write_file {"content": "x", "path": "src/a.py"}')
    led.append("tool_call", 'edit_file {"new": "n", "old": "o", "path": "src/b.py"}')
    led.append("tool_call", 'run {"cmd": "echo pwned > src/c.py"}')   # shell write: NOT witnessed
    led.append("tool_call", 'read_file {"path": "src/d.py"}')          # a read is not an edit
    assert witnessed_edit_paths(led) == ["src/a.py", "src/b.py"]
