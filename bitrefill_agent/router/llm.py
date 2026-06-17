"""Shared OpenAI-compatible LLM helper (free providers like OpenRouter).

Reuses the LLM_API_KEY / LLM_BASE_URL / LLM_MODEL config from .env. Exposes a
single chat_json() that coerces the model's reply into a parsed JSON object,
tolerant of code fences and surrounding prose.
"""

from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-120b:free"


class LLMUnavailable(RuntimeError):
    """Raised when the LLM can't be reached — callers fall back to heuristics."""


def get_llm() -> tuple[OpenAI, str]:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise LLMUnavailable("LLM_API_KEY not set")
    client = OpenAI(api_key=api_key, base_url=os.environ.get("LLM_BASE_URL"))
    return client, os.environ.get("LLM_MODEL", DEFAULT_MODEL)


def _extract_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def chat_json(system: str, user: str, *, max_tokens: int = 1200) -> Any:
    """Single-shot completion that returns parsed JSON, or raises LLMUnavailable."""
    try:
        client, model = get_llm()
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = resp.choices[0].message.content or ""
        return _extract_json(content)
    except LLMUnavailable:
        raise
    except Exception as e:  # network, rate-limit, parse — all fall back
        raise LLMUnavailable(str(e)) from e
