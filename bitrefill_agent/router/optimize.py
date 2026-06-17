"""Allocate a budget across discovered instruments — the optimization core.

Judgment (which instruments suit this destination + needs, and roughly how to
split the budget) comes from the LLM. The math (snapping each share to a REAL
denomination by settlement cost, staying under budget) is deterministic, so the
result is always purchasable. Falls back to a pure-heuristic allocator if the
LLM is unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .discover import Instrument
from .intent import RouteRequest
from .llm import LLMUnavailable, chat_json
from .policy import SpendPolicy


@dataclass
class BasketLine:
    product_id: str
    package_id: str
    kind: str
    name: str
    face_value: float
    face_label: str
    currency: str
    cost: float          # settlement-currency cost
    why: str


@dataclass
class Basket:
    lines: list[BasketLine] = field(default_factory=list)
    leftover: float = 0.0
    currency: str = "USD"
    notes: list[str] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return round(sum(line.cost for line in self.lines), 2)


def _snap(inst: Instrument, target_cost: float, remaining: float) -> tuple[str, float, float, str] | None:
    """Pick the denomination of `inst` whose cost best fits target_cost ≤ remaining.

    Returns (package_id, face_value, cost, label) or None if nothing fits.
    """
    candidates: list[tuple[str, float, float, str]] = []
    for d in inst.denoms:
        if d.cost <= remaining + 1e-6:
            candidates.append((d.package_id, d.face_value, d.cost, d.label))
    if inst.range_rate and inst.range_min is not None and inst.range_max is not None:
        # Choose a face value whose cost ≈ target, clamped to range and step.
        step = inst.range_step or 1
        face = target_cost / inst.range_rate
        face = max(inst.range_min, min(inst.range_max, face))
        face = round(face / step) * step
        cost = round(face * inst.range_rate, 2)
        if cost <= remaining + 1e-6 and cost > 0:
            pid = f"{inst.product_id}<&>{face:g}"
            candidates.append((pid, face, cost, f"{face:g}"))
    if not candidates:
        return None
    # Closest cost to target wins; ties prefer the larger (more value delivered).
    candidates.sort(key=lambda c: (abs(c[2] - target_cost), -c[2]))
    return candidates[0]


def _menu_for_llm(instruments: list[Instrument]) -> list[dict]:
    menu = []
    for i in instruments:
        costs = sorted({round(d.cost, 2) for d in i.denoms})
        if i.range_rate and i.range_min is not None:
            costs = sorted(set(costs) | {round(i.range_min * i.range_rate, 2),
                                         round((i.range_max or i.range_min) * i.range_rate, 2)})
        menu.append({
            "product_id": i.product_id,
            "name": i.name,
            "kind": i.kind,
            "currency": i.currency,
            "available_costs_usd": costs[:8],
        })
    return menu


_SYSTEM = (
    "You are a cross-border value-routing optimizer. Given a budget, a destination "
    "country, the recipient's needs, and a menu of locally-purchasable instruments "
    "(each with its settlement cost in the budget currency), choose an allocation that "
    "maximizes USEFUL, LOCALLY-REDEEMABLE value. Prefer local airtime/data, local "
    "retail gift cards, and eSIM data for travel. NEVER pick something a recipient "
    "in that country can't redeem. Spread across 2-4 instruments when sensible. "
    "Return ONLY JSON: {\"allocations\":[{\"product_id\":str,\"target_cost\":number,"
    "\"why\":str}], \"notes\":str}. target_cost is in the budget currency; the sum "
    "should be at or just under the budget."
)


def _llm_allocate(req: RouteRequest, instruments: list[Instrument]) -> tuple[list[tuple[str, float, str]], str]:
    payload = {
        "budget": req.amount,
        "currency": req.currency,
        "country": req.country,
        "needs": req.needs,
        "notes": req.notes,
        "menu": _menu_for_llm(instruments),
    }
    data = chat_json(_SYSTEM, json.dumps(payload))
    allocs = []
    for a in data.get("allocations", []):
        try:
            allocs.append((str(a["product_id"]), float(a["target_cost"]), str(a.get("why", ""))))
        except (KeyError, ValueError, TypeError):
            continue
    return allocs, str(data.get("notes", ""))


def _heuristic_allocate(req: RouteRequest, instruments: list[Instrument]) -> tuple[list[tuple[str, float, str]], str]:
    """No-LLM fallback: spread the budget over the top-scoring distinct kinds."""
    by_kind: dict[str, Instrument] = {}
    for i in sorted(instruments, key=lambda x: (-x.score, x.min_cost)):
        by_kind.setdefault(i.kind, i)
    picks = list(by_kind.values())[:3]
    if not picks:
        return [], "no instruments available"
    share = req.amount / len(picks)
    return ([(i.product_id, share, f"{i.kind} is locally redeemable in {req.country}")
             for i in picks], "heuristic allocation (LLM unavailable)")


def optimize(req: RouteRequest, instruments: list[Instrument], policy: SpendPolicy) -> Basket:
    by_id = {i.product_id: i for i in instruments}
    used_llm = True
    try:
        allocs, notes = _llm_allocate(req, instruments)
        if not allocs:
            raise LLMUnavailable("empty allocation")
    except LLMUnavailable:
        allocs, notes = _heuristic_allocate(req, instruments)
        used_llm = False

    basket = Basket(currency=req.currency, notes=[notes] if notes else [])
    if not used_llm:
        basket.notes.append("LLM unavailable — used deterministic fallback")

    remaining = min(req.amount, policy.max_per_route)
    for product_id, target_cost, why in allocs:
        inst = by_id.get(product_id)
        if inst is None or remaining <= 0:
            continue
        capped_target = min(target_cost, policy.max_per_order, remaining)
        snap = _snap(inst, capped_target, remaining)
        if snap is None:
            basket.notes.append(f"skipped {inst.name}: no denomination fits ${remaining:.2f} left")
            continue
        package_id, face, cost, label = snap
        basket.lines.append(BasketLine(
            product_id=inst.product_id, package_id=package_id, kind=inst.kind,
            name=inst.name, face_value=face, face_label=label, currency=inst.currency,
            cost=round(cost, 2), why=why,
        ))
        remaining = round(remaining - cost, 2)

    basket.leftover = round(min(req.amount, policy.max_per_route) - basket.total_cost, 2)
    return basket
