"""Milestone 6 — phone top-ups and gifting.

Phone top-ups reuse the standard invoice flow with a `phone_number` (E.164) and
return no redemption code — `delivered` means the airtime landed. Gifting on the
Personal API is limited to attaching an `email` for end-user notification; the
rich gift object (recipient name, theme, send_date) is an MCP `buy-products`
feature — see mcp_compare.py for that surface.
"""

from __future__ import annotations

from typing import Any

from .client import BitrefillClient
from .purchase import PurchaseResult, buy, log_transaction


def check_phone_number(client: BitrefillClient, phone_number: str) -> dict[str, Any]:
    """GET /check_phone_number — operators that serve this number (E.164)."""
    return client.get("/check_phone_number", params={"phone_number": phone_number})


def top_up_phone(
    client: BitrefillClient,
    product_id: str,
    phone_number: str,
    *,
    package_id: str | None = None,
    value: float | None = None,
) -> PurchaseResult:
    """Buy a phone refill for the given number. No redemption code is returned."""
    return buy(
        client,
        product_id,
        package_id=package_id,
        value=value,
        phone_number=phone_number,
    )


def gift(
    client: BitrefillClient,
    product_id: str,
    recipient_email: str,
    *,
    package_id: str | None = None,
    value: float | None = None,
    quantity: int = 1,
) -> PurchaseResult:
    """Buy a product and attach the recipient's email for notification.

    NOTE: The Personal API supports `email` for notifications only. For full
    gifting (theme, sender name, scheduled send_date) use the MCP buy-products
    `gift` object documented in mcp_compare.py.
    """
    item: dict[str, Any] = {"product_id": product_id, "quantity": quantity}
    if package_id is not None:
        item["package_id"] = package_id
    if value is not None:
        item["value"] = value

    invoice = client.post(
        "/invoices",
        json={
            "products": [item],
            "payment_method": "balance",
            "auto_pay": True,
            "email": recipient_email,
        },
    )

    # Reuse the resolution + logging shape from the core pipeline.
    from .purchase import get_order, invoice_settled, poll_invoice

    if not invoice_settled(invoice):
        invoice = poll_invoice(client, invoice["id"])
    orders = invoice.get("orders") or []
    order = get_order(client, orders[0]["id"]) if orders else None

    result = PurchaseResult(
        invoice_id=invoice["id"],
        invoice_status=invoice.get("status", "unknown"),
        order_id=(order or {}).get("id"),
        order_status=(order or {}).get("status"),
        product_id=product_id,
        redemption_info=(order or {}).get("redemption_info"),
    )
    log_transaction(result)
    return result


if __name__ == "__main__":
    from .purchase import summarize

    with BitrefillClient() as bf:
        print("=== phone top-up (test-phone-refill) ===")
        res = top_up_phone(bf, "test-phone-refill", "+15551234567", value=10)
        print(summarize(res), f"(order={res.order_status})")
