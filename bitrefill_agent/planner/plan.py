"""Turn a (safe) goal + profile into a budgeted, fundable LifePlan.

Judgment (which items, which German retailer, rough price) = LLM. Money math
(group by retailer, snap each subtotal up to a real gift-card denomination,
respect the budget) = deterministic. Reuses the DE retailer catalog.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass, field

from ..catalog import get_product
from ..client import BitrefillClient, BitrefillError
from ..router.discover import discover_instruments
from ..router.intent import RouteRequest
from ..router.llm import LLMUnavailable, chat_json
from .profile import Profile

# Anchor German retailers we always try to offer (id -> friendly + amazon flag).
ANCHOR_RETAILERS = [
    "amazon_de-germany",
    "media-markt-germany",
    "ikea-germany",
    "itunes-germany",
    "zalando-de-germany",
    "decathlon-germany",
]


@dataclass
class PlanItem:
    name: str
    category: str
    est_price_eur: float
    retailer_product_id: str
    retailer_name: str
    search_url: str
    why: str


@dataclass
class FundingCard:
    retailer_product_id: str
    retailer_name: str
    package_id: str
    denomination_eur: float
    covers_eur: float       # subtotal of items assigned to this retailer


@dataclass
class LifePlan:
    summary: str
    items: list[PlanItem] = field(default_factory=list)
    funding: list[FundingCard] = field(default_factory=list)
    budget_eur: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def items_total(self) -> float:
        return round(sum(i.est_price_eur for i in self.items), 2)

    @property
    def funding_total(self) -> float:
        return round(sum(f.denomination_eur for f in self.funding), 2)

    @property
    def within_budget(self) -> bool:
        # The spend intent (planned item prices) must fit the budget. Gift-card
        # face value may round above it; the surplus is retained balance, not spend.
        return self.items_total <= self.budget_eur + 1e-6

    @property
    def surplus_eur(self) -> float:
        return round(self.funding_total - self.items_total, 2)


# --- retailer menu -----------------------------------------------------------
@dataclass
class Retailer:
    product_id: str
    name: str
    denoms: list[float]            # available EUR face values, ascending
    package_by_value: dict[float, str]

    def smallest_covering(self, subtotal: float) -> tuple[str, float] | None:
        for v in self.denoms:
            if v + 1e-6 >= subtotal:
                return self.package_by_value[v], v
        if self.denoms:  # subtotal exceeds the largest single card
            v = self.denoms[-1]
            return self.package_by_value[v], v
        return None


def de_retailer_menu(client: BitrefillClient, *, limit: int = 30) -> list[Retailer]:
    """Curated anchors + discovered DE gift cards, as fundable retailers."""
    seen: dict[str, Retailer] = {}

    def add(product: dict) -> None:
        pid = product.get("id")
        packages = product.get("packages") or []
        denoms: dict[float, str] = {}
        for p in packages:
            try:
                denoms[float(p["value"])] = p["id"]
            except (KeyError, ValueError, TypeError):
                continue
        if not pid or not denoms or pid in seen:
            return
        seen[pid] = Retailer(
            product_id=pid,
            name=product.get("name", pid),
            denoms=sorted(denoms),
            package_by_value=denoms,
        )

    for slug in ANCHOR_RETAILERS:
        try:
            add(get_product(client, slug))
        except BitrefillError:
            continue

    # Fill out with other discovered DE gift cards.
    req = RouteRequest(amount=0, currency="EUR", country="DE")
    for inst in discover_instruments(client, req, limit=limit):
        if inst.kind != "giftcard" or inst.product_id in seen or not inst.denoms:
            continue
        denoms = {d.face_value: d.package_id for d in inst.denoms if d.face_value > 0}
        if denoms:
            seen[inst.product_id] = Retailer(inst.product_id, inst.name,
                                             sorted(denoms), denoms)
    return list(seen.values())


# Real on-site search URLs per German retailer, so every item links to actual,
# buyable products on the store where the gift card is redeemable. Matched by
# substring against the retailer's product id, with a Google fallback.
RETAILER_SEARCH = [
    ("amazon", "https://www.amazon.de/s?k={q}"),
    ("media-markt", "https://www.mediamarkt.de/de/search.html?query={q}"),
    ("ikea", "https://www.ikea.com/de/de/search/?q={q}"),
    ("decathlon", "https://www.decathlon.de/search?Ntt={q}"),
    ("zalando", "https://www.zalando.de/catalog/?q={q}"),
    ("itunes", "https://www.apple.com/de/search/{q}"),
    ("apple", "https://www.apple.com/de/search/{q}"),
    ("saturn", "https://www.saturn.de/de/search.html?query={q}"),
    ("otto", "https://www.otto.de/suche/{q}/"),
    ("h-m", "https://www2.hm.com/de_de/search-results.html?q={q}"),
    ("douglas", "https://www.douglas.de/de/search?q={q}"),
]


def _search_url(retailer_id: str, query: str) -> str:
    q = urllib.parse.quote_plus(query)
    for key, template in RETAILER_SEARCH:
        if key in retailer_id:
            return template.format(q=q)
    return f"https://www.google.com/search?q={q}"


_SYSTEM = (
    "You are a careful life-planning shopping agent for someone in Germany (EUR). Given a "
    "GOAL, the person's budget + health/finance signals, and a menu of German retailers you "
    "can fund via gift cards, propose 3-6 concrete, helpful purchases that advance the goal "
    "WITHIN budget. Map each item to the most fitting retailer from the menu (Amazon.de for "
    "general goods, MediaMarkt for electronics, IKEA for home, etc.). Be realistic about EUR "
    "prices. Respect the discretionary budget as a hard cap on the SUM of item prices. "
    "Where easy, group items so each retailer's subtotal lands near one of its gift-card "
    "denominations, to minimize leftover balance. "
    "Return ONLY JSON: {\"items\": [{\"name\": str, \"category\": str, \"est_price_eur\": "
    "number, \"retailer_product_id\": str (from the menu), \"why\": str}], \"summary\": str}."
)


def build_plan(
    client: BitrefillClient, goal: str, profile: Profile, *, menu: list[Retailer] | None = None
) -> LifePlan:
    menu = menu or de_retailer_menu(client)
    by_id = {r.product_id: r for r in menu}

    payload = {
        "goal": goal,
        "budget_eur": profile.monthly_discretionary,
        "signals": profile.summary(),
        "retailers": [
            {"product_id": r.product_id, "name": r.name, "denominations_eur": r.denoms}
            for r in menu
        ],
    }

    notes: list[str] = []
    try:
        data = chat_json(_SYSTEM, json.dumps(payload))
        raw_items = data.get("items", [])
        summary = str(data.get("summary", goal))
    except (LLMUnavailable, json.JSONDecodeError, KeyError, TypeError):
        raw_items, summary = [], goal
        notes.append("LLM unavailable — returning an empty plan; try again shortly.")

    items: list[PlanItem] = []
    for it in raw_items:
        rid = str(it.get("retailer_product_id", ""))
        retailer = by_id.get(rid)
        if retailer is None:
            # snap to Amazon.de if the model named an off-menu retailer
            retailer = by_id.get("amazon_de-germany") or (menu[0] if menu else None)
            if retailer is None:
                continue
            rid = retailer.product_id
        try:
            price = float(it.get("est_price_eur", 0))
        except (ValueError, TypeError):
            price = 0.0
        name = str(it.get("name", "item"))
        items.append(PlanItem(
            name=name,
            category=str(it.get("category", "")),
            est_price_eur=round(price, 2),
            retailer_product_id=rid,
            retailer_name=retailer.name,
            search_url=_search_url(rid, name),
            why=str(it.get("why", "")),
        ))

    plan = LifePlan(summary=summary, items=items,
                    budget_eur=profile.monthly_discretionary, notes=notes)
    _compute_funding(plan, by_id)
    return plan


def _compute_funding(plan: LifePlan, by_id: dict[str, Retailer]) -> None:
    """Group items by retailer, snap each subtotal up to a real gift-card denom."""
    subtotals: dict[str, float] = {}
    for it in plan.items:
        subtotals[it.retailer_product_id] = subtotals.get(it.retailer_product_id, 0) + it.est_price_eur

    for rid, subtotal in subtotals.items():
        retailer = by_id.get(rid)
        if retailer is None:
            continue
        snap = retailer.smallest_covering(round(subtotal, 2))
        if snap is None:
            plan.notes.append(f"{retailer.name}: no gift-card denomination available")
            continue
        package_id, denom = snap
        if denom + 1e-6 < subtotal:
            plan.notes.append(
                f"{retailer.name}: items total €{subtotal:.2f} exceeds the largest single "
                f"card (€{denom:.0f}); buying €{denom:.0f} and leaving a shortfall."
            )
        plan.funding.append(FundingCard(rid, retailer.name, package_id, denom, round(subtotal, 2)))

    if plan.surplus_eur > 0.5:
        plan.notes.append(
            f"gift cards come in fixed denominations, so €{plan.funding_total:.0f} of cards "
            f"fund €{plan.items_total:.0f} of planned items; the €{plan.surplus_eur:.0f} "
            f"surplus stays as redeemable balance for next time."
        )
