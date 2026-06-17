"""Parse a free-text intent into a structured RouteRequest.

LLM-first (it resolves "my brother in Lagos" -> country NG), with a small
regex fallback so the demo degrades gracefully if the model is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .llm import LLMUnavailable, chat_json

# Minimal country-name -> ISO2 map for the heuristic fallback.
_COUNTRY_HINTS = {
    "nigeria": "NG", "lagos": "NG", "abuja": "NG",
    "japan": "JP", "tokyo": "JP",
    "india": "IN", "kenya": "KE", "nairobi": "KE",
    "usa": "US", "united states": "US", "america": "US",
    "uk": "GB", "britain": "GB", "london": "GB",
    "philippines": "PH", "manila": "PH", "mexico": "MX",
    "brazil": "BR", "germany": "DE", "france": "FR", "spain": "ES",
}

_SYSTEM = (
    "You convert a money-sending intent into strict JSON. Resolve the destination "
    "to an ISO 3166-1 alpha-2 country code. Output ONLY a JSON object with keys: "
    "amount (number), currency (3-letter, default USD), country (ISO2 uppercase), "
    "recipient_phone (E.164 string or null), needs (array of short strings like "
    '"airtime","data","groceries","gaming","travel"), notes (string). '
    "Infer needs from the text; empty array if unstated."
)


@dataclass
class RouteRequest:
    amount: float
    currency: str
    country: str
    recipient_phone: str | None = None
    needs: list[str] = field(default_factory=list)
    notes: str = ""
    raw: str = ""


def _fallback(text: str) -> RouteRequest:
    m = re.search(r"([$€£])?\s*(\d+(?:\.\d+)?)", text)
    amount = float(m.group(2)) if m else 25.0
    cur = {"$": "USD", "€": "EUR", "£": "GBP"}.get(m.group(1) if m else "", "USD")
    country = "US"
    low = text.lower()
    for name, iso in _COUNTRY_HINTS.items():
        if name in low:
            country = iso
            break
    phone = None
    pm = re.search(r"\+\d{7,15}", text)
    if pm:
        phone = pm.group(0)
    needs = [n for n in ("airtime", "data", "groceries", "gaming", "travel")
             if n in low or (n == "data" and "esim" in low)]
    return RouteRequest(amount, cur, country, phone, needs, "heuristic parse", text)


def parse_intent(text: str) -> RouteRequest:
    try:
        d = chat_json(_SYSTEM, text)
        return RouteRequest(
            amount=float(d["amount"]),
            currency=str(d.get("currency", "USD")).upper()[:3],
            country=str(d["country"]).upper()[:2],
            recipient_phone=d.get("recipient_phone") or None,
            needs=[str(n) for n in (d.get("needs") or [])],
            notes=str(d.get("notes", "")),
            raw=text,
        )
    except (LLMUnavailable, KeyError, ValueError, TypeError):
        return _fallback(text)
