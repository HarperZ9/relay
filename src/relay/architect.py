"""architect.py — plan with one model, implement with another.

A named, real gap versus aider: its Architect Mode has a stronger/slower model
describe a change in plain language, then a faster/cheaper model turns that plan
into edits. This is the model-agnostic version, built on relay's own multi-
backend ladder: the planner is just another `prefer`-selected backend, so ANY
two tiers relay already reaches (local, subscription, api) can pair up, not
just two named frontier models. The plan is a proposal fed to the implementer
as context, never a substitute for the implementer's own tool use — the
implementer still reads the real code and may deviate if the plan is wrong.
"""
from __future__ import annotations

_PLAN_PROMPT = (
    "You are planning a code change, not writing it. Read the task below and "
    "describe a concise, concrete step-by-step plan: which files to touch, what "
    "functions to add or change, and the approach. Do not write code and do not "
    "emit any TOOL line; a separate step will implement your plan.\n\nTask: {goal}"
)


def plan(planner, goal: str) -> dict:
    """Ask `planner` (anything with .send(text) -> the LocalAgent response shape)
    for a plan. Returns {"text", "backend"}. A BackendError here is the caller's
    to handle, same as any other turn — this function does not swallow it."""
    resp = planner.send(_PLAN_PROMPT.format(goal=goal))
    text = resp["content"][0]["text"] if resp.get("content") else ""
    return {"text": text, "backend": resp.get("backend", "?")}


def with_plan(goal: str, planned: dict) -> str:
    """The implementer's goal: the original task plus the planner's proposal,
    explicit that it is a proposal the implementer may adapt, never dictates."""
    return (f"{goal}\n\nA planning pass ({planned['backend']}) proposed this "
           f"approach:\n{planned['text']}\n\nImplement it. Adapt if you find a "
           f"better path once you inspect the actual code.")
