"""Falsifiers for architect mode (parity with aider's Architect Mode).

Load-bearing: (1) the planner is asked to plan, not implement (no TOOL lines
solicited); (2) the plan is a PROPOSAL folded into the goal, never a silent
replacement of it; (3) the planner's backend attribution is carried through so
a reader knows which tier planned; (4) a planner that errors raises past `plan`
uncaught (the CLI's problem to surface, never swallowed here); (5) end-to-end
via the CLI, --architect actually changes what the implementer is sent, and a
dead planner backend fails loud rather than silently skipping the plan.
"""
import pytest

from relay.architect import plan, with_plan
from relay.local_agent import BackendError


class _Planner:
    def __init__(self, text="", backend="claude-plan", raise_on_send=None):
        self.text, self.backend, self._raise = text, backend, raise_on_send
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        if self._raise:
            raise self._raise
        return {"content": [{"type": "text", "text": self.text}], "backend": self.backend}


def test_plan_asks_to_plan_not_implement():
    p = _Planner("1. add a helper\n2. wire it in")
    result = plan(p, "add caching to fetch()")
    assert "do not write code" in p.sent[0].lower()
    assert "do not" in p.sent[0].lower() and "tool" in p.sent[0].lower()  # told NOT to use tools
    assert "add caching to fetch()" in p.sent[0]
    assert result == {"text": "1. add a helper\n2. wire it in", "backend": "claude-plan"}


def test_with_plan_folds_the_proposal_into_the_goal_not_over_it():
    goal = "add caching to fetch()"
    out = with_plan(goal, {"text": "1. add a helper", "backend": "claude-plan"})
    assert out.startswith(goal)                 # the original task survives, unaltered, up front
    assert "1. add a helper" in out
    assert "claude-plan" in out                  # attribution: which tier planned
    assert "adapt" in out.lower()                # explicit: a proposal, not a mandate


def test_planner_backend_attribution_survives_into_the_folded_goal():
    out = with_plan("x", plan(_Planner("do y", backend="codex-api"), "x"))
    assert "codex-api" in out


def test_empty_plan_response_does_not_crash_or_fabricate_content():
    result = plan(_Planner(""), "x")
    assert result["text"] == ""
    out = with_plan("x", result)
    assert "x" in out                            # still composes cleanly on an empty plan


def test_a_failing_planner_raises_past_plan_uncaught():
    with pytest.raises(BackendError):
        plan(_Planner(raise_on_send=BackendError("all backends down")), "x")


def test_cli_architect_backend_defaults_to_none(monkeypatch):
    from relay import local_agent_cli as cli

    class _Live:
        def live_backend(self):
            return object()
    seen = {}
    monkeypatch.setattr(cli, "_build_agent", lambda args: _Live())
    monkeypatch.setattr(cli, "run_agent",
                        lambda agent, goal, *a, **k: (seen.update(goal=goal),
                                                      {"final": "done", "steps": 1, "entries": 1,
                                                       "checkpoint": "c" * 32, "verified": True,
                                                       "accepted": True, "check_passed": None,
                                                       "integrity": {"clean": True, "flag_count": 0},
                                                       "review": {"reviewability": 1.0, "edited_unread": [],
                                                                  "unverified_edits": [], "failed_calls": 0},
                                                       "risk": {"demands": []}})[1])
    rc = cli.main(["do the thing", "--agent", "--root", "."])
    assert rc == 0
    assert seen["goal"] == "do the thing"   # no --architect -> the goal is untouched


def test_cli_architect_folds_a_plan_into_the_goal_end_to_end(monkeypatch):
    from relay import local_agent_cli as cli

    class _Live:
        def live_backend(self):
            return object()

    class _Planner:
        def live_backend(self):
            return object()

        def send(self, message):
            return {"content": [{"type": "text", "text": "1. rename the function"}],
                    "backend": "claude-plan"}

    seen = {}
    monkeypatch.setattr(cli, "_build_agent", lambda args: _Live())
    monkeypatch.setattr(cli, "LocalAgent", lambda *a, **k: _Planner())
    monkeypatch.setattr(cli, "run_agent",
                        lambda agent, goal, *a, **k: (seen.update(goal=goal),
                                                      {"final": "done", "steps": 1, "entries": 1,
                                                       "checkpoint": "c" * 32, "verified": True,
                                                       "accepted": True, "check_passed": None,
                                                       "integrity": {"clean": True, "flag_count": 0},
                                                       "review": {"reviewability": 1.0, "edited_unread": [],
                                                                  "unverified_edits": [], "failed_calls": 0},
                                                       "risk": {"demands": []}})[1])
    rc = cli.main(["do the thing", "--agent", "--root", ".", "--architect", "claude-plan"])
    assert rc == 0
    assert "do the thing" in seen["goal"] and "rename the function" in seen["goal"]
    assert "claude-plan" in seen["goal"]


def test_cli_architect_with_dead_planner_fails_loud_not_silently_skipped(monkeypatch):
    from relay import local_agent_cli as cli

    class _Live:
        def live_backend(self):
            return object()

    class _DeadPlanner:
        def live_backend(self):
            return None
    monkeypatch.setattr(cli, "_build_agent", lambda args: _Live())
    monkeypatch.setattr(cli, "LocalAgent", lambda *a, **k: _DeadPlanner())
    rc = cli.main(["do the thing", "--agent", "--root", ".", "--architect", "codex-plan"])
    assert rc == 1   # never silently degrades to "no plan" -- the operator asked for one
