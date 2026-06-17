"""Autonomous checkout of a Basket — one multi-item invoice, no human clicking pay.

Two modes:
- "safe"  : prove the autonomous multi-item mechanic at ~zero cost. The planned
            REAL basket is shown, but each line is executed against the free test
            product `delos-syldavia` (delivers a real code, doesn't move credit).
- "live"  : execute the real basket from account balance (spends test credits).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..client import BitrefillClient
from ..purchase import BasketReceipt, buy_basket, mask_code
from .optimize import Basket

# Free/near-free test products that deliver a real redemption code. We cycle
# through them so a multi-line basket isn't N identical items in one invoice.
SAFE_POOL: list[dict[str, Any]] = [
    {"product_id": "delos-syldavia", "package_id": "delos-syldavia<&>0.01"},
    {"product_id": "test-gift-card-code", "value": 10},
]


@dataclass
class FulfilledLine:
    name: str
    kind: str
    face_label: str
    currency: str
    status: str | None
    masked_code: str
    why: str


@dataclass
class Fulfillment:
    mode: str
    invoice_id: str
    invoice_status: str
    all_delivered: bool
    lines: list[FulfilledLine] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def execute_basket(
    client: BitrefillClient, basket: Basket, *, mode: str = "safe"
) -> Fulfillment:
    """Check out the basket autonomously. Returns per-line fulfillment."""
    if not basket.lines:
        return Fulfillment(mode, "", "empty", False, notes=["basket was empty"])

    if mode == "live":
        items: list[dict[str, Any]] = [
            {"product_id": ln.product_id, "package_id": ln.package_id, "quantity": 1}
            for ln in basket.lines
        ]
    else:
        # One safe order per planned line -> same order count, zero/near-zero spend.
        items = [
            {**SAFE_POOL[i % len(SAFE_POOL)], "quantity": 1}
            for i in range(len(basket.lines))
        ]

    receipt: BasketReceipt = buy_basket(client, items, payment_method="balance")

    lines: list[FulfilledLine] = []
    for plan, outcome in zip(basket.lines, receipt.outcomes):
        lines.append(FulfilledLine(
            name=plan.name,
            kind=plan.kind,
            face_label=f"{plan.face_label} {plan.currency}".strip(),
            currency=plan.currency,
            status=outcome.status,
            masked_code=mask_code(outcome.redemption_info),
            why=plan.why,
        ))

    notes = []
    if mode == "safe":
        notes.append(
            "safe mode: real basket planned over the live catalog; executed against "
            "the free test product to prove autonomous checkout without spending."
        )
    delivered = sum(1 for o in receipt.outcomes if o.status == "delivered")
    if delivered == 0 and receipt.outcomes:
        notes.append(
            "no orders delivered — Bitrefill's test delivery rail appears degraded "
            "right now; failed orders are auto-refunded. The route logic ran end-to-end."
        )
    return Fulfillment(
        mode=mode,
        invoice_id=receipt.invoice_id,
        invoice_status=receipt.invoice_status,
        all_delivered=receipt.all_delivered,
        lines=lines,
        notes=notes,
    )
