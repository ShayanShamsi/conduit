"""Stateless multi-turn controller for the planner.

Given the conversation history + profile, decide the next agent turn:
  - refuse  : the goal is unsafe (safety guardrail) → explain + safe alternative
  - clarify : need 1-2 details before planning → ask short questions
  - plan    : enough context → produce a budgeted LifePlan

History is passed in each call (the web client keeps it), so this stays stateless.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from ..client import BitrefillClient
from ..router.llm import LLMUnavailable, chat_json
from .plan import LifePlan, build_plan
from .profile import Profile
from .safety import check_goal


@dataclass
class Turn:
    type: str                       # "refuse" | "clarify" | "plan"
    message: str = ""
    questions: list[str] = field(default_factory=list)
    plan: dict[str, Any] | None = None


def _first_user_goal(history: list[dict[str, str]]) -> str:
    for m in history:
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def _all_user_text(history: list[dict[str, str]]) -> str:
    return "\n".join(m.get("content", "") for m in history if m.get("role") == "user")


_CLARIFY_SYSTEM = (
    "You are a life-planning shopping agent (Germany, EUR). Decide if you have enough to "
    "propose a concrete shopping plan toward the user's goal, or if ONE short round of "
    "clarifying questions would materially improve it (e.g. home vs gym, space, preferences). "
    "Given the conversation so far, return ONLY JSON: "
    '{"ready": true|false, "questions": [up to 2 short strings]}. '
    "Prefer ready=true once the goal and basic context are clear; never ask more than twice."
)


def _needs_clarify(history: list[dict[str, str]]) -> list[str]:
    # Only consider clarifying on the very first turn; after that, just plan.
    user_turns = sum(1 for m in history if m.get("role") == "user")
    if user_turns >= 2:
        return []
    try:
        d = chat_json(_CLARIFY_SYSTEM, json.dumps(history), max_tokens=300)
        if d.get("ready", True):
            return []
        return [str(q) for q in (d.get("questions") or [])][:2]
    except (LLMUnavailable, json.JSONDecodeError, KeyError, TypeError):
        return []


def _plan_to_dict(plan: LifePlan) -> dict[str, Any]:
    return {
        "summary": plan.summary,
        "budget_eur": plan.budget_eur,
        "items_total": plan.items_total,
        "funding_total": plan.funding_total,
        "surplus_eur": plan.surplus_eur,
        "within_budget": plan.within_budget,
        "items": [asdict(i) for i in plan.items],
        "funding": [asdict(f) for f in plan.funding],
        "notes": plan.notes,
    }


def next_turn(
    history: list[dict[str, str]],
    profile: Profile,
    *,
    client: BitrefillClient | None = None,
) -> Turn:
    """Compute the next agent turn from the conversation so far."""
    goal = _all_user_text(history)
    if not goal.strip():
        return Turn("clarify", message="What life goal can I help you work toward?")

    # 1. Safety first — on the full user input.
    verdict = check_goal(goal)
    if not verdict.safe:
        msg = verdict.reason or "I can't help purchase for that goal."
        if verdict.alternative:
            msg += "\n\n" + verdict.alternative
        return Turn("refuse", message=msg)

    # 2. Maybe one round of clarifying questions.
    questions = _needs_clarify(history)
    if questions:
        return Turn(
            "clarify",
            message="A couple of quick questions so I plan the right things:",
            questions=questions,
        )

    # 3. Plan.
    own = client is None
    client = client or BitrefillClient()
    try:
        plan = build_plan(client, _first_user_goal(history) or goal, profile)
    finally:
        if own:
            client.close()
    return Turn(
        "plan",
        message=plan.summary or "Here's a plan within your budget:",
        plan=_plan_to_dict(plan),
    )
