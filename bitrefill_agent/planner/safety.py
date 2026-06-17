"""Goal safety guardrail.

A deterministic keyword backstop catches the obvious harmful asks even if the
LLM is unavailable; the LLM classifier handles nuance and proposes a safe
alternative. converse.py calls check_goal() on every user turn before planning.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..router.llm import LLMUnavailable, chat_json

# Fast backstop — phrases that should never reach planning/funding.
_BLOCK_PATTERNS = [
    r"\b(suicide|kill myself|self[- ]?harm|hurt myself|end my life)\b",
    r"\b(weapon|gun|firearm|ammunition|explosive|bomb|silencer)\b",
    r"\b(meth|cocaine|heroin|fentanyl|illegal drugs?)\b",
    r"\b(hurt|harm|attack|poison|stalk)\s+(someone|somebody|him|her|them|my)\b",
    r"\b(counterfeit|launder|stolen cards?|carding)\b",
]


@dataclass
class SafetyVerdict:
    safe: bool
    reason: str = ""
    alternative: str = ""


_SYSTEM = (
    "You are a safety reviewer for a shopping-planner agent that buys consumer goods "
    "(fitness, sleep, study, hobbies, home) via gift cards. Decide if a user's GOAL is "
    "safe to plan purchases for. Unsafe = self-harm, weapons, illegal drugs, harming "
    "others, illegal/fraudulent activity, or anything dangerous. Most everyday wellness, "
    "study, hobby, and home goals are SAFE. Return ONLY JSON: "
    '{"safe": true|false, "reason": str, "alternative": str}. '
    "If unsafe, reason explains why briefly and alternative offers a constructive, safe "
    "redirection. If safe, leave reason/alternative empty."
)


def _keyword_block(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in _BLOCK_PATTERNS)


def check_goal(goal_text: str) -> SafetyVerdict:
    if _keyword_block(goal_text):
        return SafetyVerdict(
            safe=False,
            reason="This goal involves harm or illegal activity, which I can't help purchase for.",
            alternative="If you're going through something difficult, please reach out to a "
            "professional or a helpline. I'm happy to help with health, study, or hobby goals.",
        )
    try:
        d = chat_json(_SYSTEM, goal_text, max_tokens=400)
        return SafetyVerdict(
            safe=bool(d.get("safe", True)),
            reason=str(d.get("reason", "")),
            alternative=str(d.get("alternative", "")),
        )
    except (LLMUnavailable, json.JSONDecodeError, KeyError, TypeError):
        # LLM down: keyword backstop already passed, so allow but stay cautious.
        return SafetyVerdict(safe=True)
