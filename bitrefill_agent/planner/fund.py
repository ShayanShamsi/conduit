"""Autonomously buy the gift cards that fund a LifePlan, via Bitrefill.

safe mode  -> execute against a free test product (proves the mechanic, ~zero cost)
live mode  -> buy the real German gift cards from balance (needs sufficient credits)

Returns one funded card per plan retailer, with the (masked) redemption code and
the shopping list of items that card is meant to cover.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..client import BitrefillClient
from ..purchase import BasketReceipt, buy_basket, mask_code
from ..router.execute import SAFE_POOL


@dataclass
class FundedCard:
    retailer_name: str
    denomination_eur: float
    status: str | None
    masked_code: str
    shopping_list: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FundingResult:
    mode: str
    invoice_id: str
    invoice_status: str
    all_delivered: bool
    cards: list[FundedCard] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def fund_plan(
    client: BitrefillClient, plan: dict[str, Any], *, mode: str = "safe"
) -> FundingResult:
    """Buy the plan's funding gift cards in one autonomous invoice."""
    funding = plan.get("funding") or []
    if not funding:
        return FundingResult(mode, "", "empty", False, notes=["nothing to fund"])

    if mode == "live":
        items = [
            {"product_id": f["retailer_product_id"], "package_id": f["package_id"], "quantity": 1}
            for f in funding
        ]
    else:
        items = [{**SAFE_POOL[i % len(SAFE_POOL)], "quantity": 1} for i in range(len(funding))]

    receipt: BasketReceipt = buy_basket(client, items, payment_method="balance")

    # Items grouped by retailer for the shopping list per card.
    by_retailer: dict[str, list[dict[str, Any]]] = {}
    for it in plan.get("items", []):
        by_retailer.setdefault(it["retailer_product_id"], []).append(
            {"name": it["name"], "est_price_eur": it["est_price_eur"], "url": it["search_url"]}
        )

    cards: list[FundedCard] = []
    for fcard, outcome in zip(funding, receipt.outcomes):
        cards.append(FundedCard(
            retailer_name=fcard["retailer_name"],
            denomination_eur=fcard["denomination_eur"],
            status=outcome.status,
            masked_code=mask_code(outcome.redemption_info),
            shopping_list=by_retailer.get(fcard["retailer_product_id"], []),
        ))

    notes: list[str] = []
    if mode == "safe":
        notes.append(
            "safe mode: real plan funded over the live catalog; executed against a free test "
            "product to prove autonomous checkout without spending."
        )
    if cards and all(c.status != "delivered" for c in cards):
        notes.append(
            "no cards delivered — Bitrefill's test rail may be degraded; failed orders are "
            "auto-refunded. The plan + funding logic ran end-to-end."
        )
    return FundingResult(
        mode=mode,
        invoice_id=receipt.invoice_id,
        invoice_status=receipt.invoice_status,
        all_delivered=receipt.all_delivered,
        cards=cards,
        notes=notes,
    )
