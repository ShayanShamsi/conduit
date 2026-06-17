"""Milestones 3 & 4 — the scripted purchase pipeline.

buy() composes: balance check -> create+pay invoice -> poll to final state ->
fetch order -> return redemption info. Plus an append-only audit log that never
records the raw redemption code, and an idempotency guard against double-handling.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import BitrefillClient, BitrefillError

LOG_PATH = Path(__file__).resolve().parent.parent / "log" / "transactions.jsonl"

# Terminal *order* states — the ground truth for "this order is done". Polling
# settles when every order reaches one of these, which is robust to whatever
# rollup label the invoice uses (complete / all_delivered / partial / ...).
TERMINAL_ORDER_STATUSES = {"delivered", "failed", "permanent_failure", "refunded"}

# Terminal *invoice* states that can settle with NO deliverable orders — payment
# rejections. We still honor these so a denied/blocked invoice stops polling even
# though its orders never progress.
TERMINAL_PAYMENT_STATUSES = {"denied", "payment_error", "blocked"}

# Kept for back-compat / readability: invoice-level rollups we've seen go final.
FINAL_INVOICE_STATUSES = {
    "complete",
    "all_delivered",
    "partial",
    "all_error",
} | TERMINAL_PAYMENT_STATUSES


def invoice_settled(invoice: dict[str, Any]) -> bool:
    """True when the invoice has reached a state worth acting on.

    Order-based: settled when there's at least one order and all orders are in a
    terminal state. Falls back to payment-rejection invoice statuses for invoices
    that never produce orders.
    """
    if invoice.get("status") in TERMINAL_PAYMENT_STATUSES:
        return True
    orders = invoice.get("orders") or []
    return bool(orders) and all(
        o.get("status") in TERMINAL_ORDER_STATUSES for o in orders
    )

# Friendly messages for the documented invoice-creation error codes.
ERROR_HINTS = {
    "not_found": "Product doesn't exist — check the product id.",
    "out_of_stock": "Product is currently unavailable — try later.",
    "invalid_param": "A parameter has the wrong type or value.",
    "invalid_value": "Value is outside the product's allowed range/packages.",
    "invalid_package_id": "That package_id doesn't exist for this product.",
    "balance_too_low": "Insufficient account balance — add funds or use crypto.",
    "too_many_items": "More than 20 items in one invoice — split it up.",
    "missing_param": "A required parameter is missing.",
}


@dataclass
class PurchaseResult:
    invoice_id: str
    invoice_status: str
    order_id: str | None
    order_status: str | None
    product_id: str
    redemption_info: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def delivered(self) -> bool:
        return self.order_status == "delivered"


# --- audit log ---------------------------------------------------------------
def _redact(info: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip sensitive redemption fields before logging."""
    if not info:
        return info
    secret = {"code", "pin", "link", "barcode_value"}
    return {k: ("<redacted>" if k in secret else v) for k, v in info.items()}


def log_transaction(result: PurchaseResult) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "invoice_id": result.invoice_id,
        "product_id": result.product_id,
        "invoice_status": result.invoice_status,
        "order_status": result.order_status,
        "redemption": _redact(result.redemption_info),
    }
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def already_processed(invoice_id: str) -> bool:
    """Idempotency guard: have we logged a final entry for this invoice?"""
    if not LOG_PATH.exists():
        return False
    with LOG_PATH.open() as fh:
        for line in fh:
            try:
                if json.loads(line).get("invoice_id") == invoice_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


# --- pipeline steps ----------------------------------------------------------
def create_invoice(
    client: BitrefillClient,
    product_id: str,
    *,
    package_id: str | None = None,
    value: float | None = None,
    quantity: int = 1,
    phone_number: str | None = None,
    auto_pay: bool = True,
) -> dict[str, Any]:
    """POST /invoices for a single product using account balance."""
    item: dict[str, Any] = {"product_id": product_id, "quantity": quantity}
    if package_id is not None:
        item["package_id"] = package_id
    if value is not None:
        item["value"] = value
    if phone_number is not None:
        item["phone_number"] = phone_number

    body = {
        "products": [item],
        "payment_method": "balance",
        "auto_pay": auto_pay,
    }
    return client.post("/invoices", json=body)


def poll_invoice(
    client: BitrefillClient,
    invoice_id: str,
    *,
    max_attempts: int = 30,
    delay: float = 2.0,
) -> dict[str, Any]:
    """GET /invoices/{id} until it settles (all orders terminal) or attempts run out."""
    invoice: dict[str, Any] = {}
    for _ in range(max_attempts):
        invoice = client.get(f"/invoices/{invoice_id}")
        if invoice_settled(invoice):
            return invoice
        time.sleep(delay)
    return invoice  # last seen, even if not settled


def get_order(client: BitrefillClient, order_id: str) -> dict[str, Any]:
    """GET /orders/{id} — includes redemption_info once delivered."""
    return client.get(f"/orders/{order_id}")


# --- multi-item baskets (the value-router checkout) --------------------------
@dataclass
class OrderOutcome:
    """One delivered/failed order within a basket."""

    order_id: str | None
    product_id: str
    status: str | None
    redemption_info: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def delivered(self) -> bool:
        return self.status == "delivered"


@dataclass
class BasketReceipt:
    invoice_id: str
    invoice_status: str
    payment_method: str
    payment_link: str | None
    outcomes: list[OrderOutcome]

    @property
    def all_delivered(self) -> bool:
        return bool(self.outcomes) and all(o.delivered for o in self.outcomes)


def buy_basket(
    client: BitrefillClient,
    items: list[dict[str, Any]],
    *,
    payment_method: str = "balance",
    return_payment_link: bool = False,
    refund_address: str | None = None,
) -> BasketReceipt:
    """Create ONE invoice for many products and check out autonomously.

    `items` is a list of product dicts, each: {product_id, package_id?, value?,
    quantity?, phone_number?, gift?}. For balance, the invoice auto-pays. For a
    crypto method we pass return_payment_link so the caller gets a link (the
    crypto-test product delivers without it ever being paid).
    """
    body: dict[str, Any] = {"products": items, "payment_method": payment_method}
    if payment_method == "balance":
        body["auto_pay"] = True
    else:
        body["return_payment_link"] = return_payment_link
        if refund_address:
            body["refund_address"] = refund_address

    try:
        invoice = client.post("/invoices", json=body)
    except BitrefillError as e:
        raise BitrefillError(
            e.status_code, e.error_code, ERROR_HINTS.get(e.error_code or "", e.message)
        ) from e

    invoice_id = invoice["id"]
    if not invoice_settled(invoice):
        invoice = poll_invoice(client, invoice_id)

    outcomes: list[OrderOutcome] = []
    for summary in invoice.get("orders") or []:
        order = get_order(client, summary["id"])
        outcome = OrderOutcome(
            order_id=order.get("id"),
            product_id=(order.get("product") or {}).get("id", "?"),
            status=order.get("status"),
            redemption_info=order.get("redemption_info"),
        )
        outcomes.append(outcome)
        # Reuse the audit log, one redacted line per order.
        log_transaction(
            PurchaseResult(
                invoice_id=invoice_id,
                invoice_status=invoice.get("status", "unknown"),
                order_id=outcome.order_id,
                order_status=outcome.status,
                product_id=outcome.product_id,
                redemption_info=outcome.redemption_info,
            )
        )

    payment = invoice.get("payment") or {}
    return BasketReceipt(
        invoice_id=invoice_id,
        invoice_status=invoice.get("status", "unknown"),
        payment_method=payment_method,
        payment_link=invoice.get("payment_link") or payment.get("payment_link"),
        outcomes=outcomes,
    )


def buy(
    client: BitrefillClient,
    product_id: str,
    *,
    package_id: str | None = None,
    value: float | None = None,
    quantity: int = 1,
    phone_number: str | None = None,
) -> PurchaseResult:
    """End-to-end purchase of one product, paid from balance."""
    try:
        invoice = create_invoice(
            client,
            product_id,
            package_id=package_id,
            value=value,
            quantity=quantity,
            phone_number=phone_number,
        )
    except BitrefillError as e:
        hint = ERROR_HINTS.get(e.error_code or "", e.message)
        raise BitrefillError(e.status_code, e.error_code, hint) from e

    invoice_id = invoice["id"]
    if not invoice_settled(invoice):
        invoice = poll_invoice(client, invoice_id)

    orders = invoice.get("orders") or []
    order_summary = orders[0] if orders else None

    redemption: dict[str, Any] | None = None
    order_status: str | None = None
    order_id: str | None = None
    if order_summary:
        order_id = order_summary["id"]
        order = get_order(client, order_id)
        order_status = order.get("status")
        redemption = order.get("redemption_info")

    result = PurchaseResult(
        invoice_id=invoice_id,
        invoice_status=invoice.get("status", "unknown"),
        order_id=order_id,
        order_status=order_status,
        product_id=product_id,
        redemption_info=redemption,
    )
    log_transaction(result)
    return result


def mask_code(info: dict[str, Any] | None) -> str:
    """Mask a redemption code/pin for display: never reveal the full secret."""
    if not info:
        return "(no code)"
    secret = info.get("code") or info.get("pin")
    if not secret:
        return "(see order)"
    secret = str(secret)
    return f"{secret[:4]}…{secret[-2:]}" if len(secret) > 6 else "•••"


def summarize(result: PurchaseResult) -> str:
    """A redacted, human-friendly one-liner. Never prints the full code."""
    if result.delivered and result.redemption_info:
        masked = mask_code(result.redemption_info)
        return (
            f"✅ delivered {result.product_id} "
            f"[invoice {result.invoice_id}] code={masked}"
        )
    if result.delivered:
        return f"✅ delivered {result.product_id} (no code — balance applied)"
    return (
        f"⚠️  {result.product_id} not delivered "
        f"(invoice={result.invoice_status}, order={result.order_status})"
    )


if __name__ == "__main__":
    with BitrefillClient() as bf:
        bal = bf.balance()
        print(f"balance: {bal.get('balance')} {bal.get('currency')}")

        print("\n-- happy path (test-gift-card-code) --")
        print(summarize(buy(bf, "test-gift-card-code", value=10)))

        print("\n-- failure path (test-gift-card-code-fail) --")
        print(summarize(buy(bf, "test-gift-card-code-fail", value=10)))
