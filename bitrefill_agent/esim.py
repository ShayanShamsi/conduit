"""Milestone 6 — eSIMs.

eSIMs use dedicated endpoints and string package values ("3GB, 30 Days"):
    GET  /products/esims            list eSIM products
    GET  /products/esims/{id}       product detail with packages
    POST /esims                     purchase a new eSIM (or top up with esim_id)
    GET  /esims                     list your eSIMs
    GET  /esims/{id}                one eSIM (ICCID), incl. package_history

The install QR is returned as redemption_info.barcode_value on the order.
"""

from __future__ import annotations

from typing import Any

from .client import BitrefillClient
from .purchase import get_order, invoice_settled, poll_invoice


def list_esim_products(client: BitrefillClient) -> list[dict[str, Any]]:
    return client.get("/products/esims")


def get_esim_product(client: BitrefillClient, product_id: str) -> dict[str, Any]:
    return client.get(f"/products/esims/{product_id}")


def list_my_esims(client: BitrefillClient) -> list[dict[str, Any]]:
    return client.get("/esims")


def get_esim(client: BitrefillClient, esim_id: str) -> dict[str, Any]:
    """GET /esims/{iccid} — includes package_history."""
    return client.get(f"/esims/{esim_id}")


def buy_esim(
    client: BitrefillClient,
    product_id: str,
    value: str,
    *,
    esim_id: str | None = None,
    quantity: int = 1,
) -> dict[str, Any]:
    """POST /esims. Omit esim_id for a new eSIM; include it to top up an existing one.

    Returns a dict with the invoice, the resolved order, and (for new eSIMs) the
    install barcode pulled from the order's redemption_info.
    """
    item: dict[str, Any] = {
        "product_id": product_id,
        "value": value,
        "quantity": quantity,
    }
    if esim_id is not None:
        item["esim_id"] = esim_id  # top-up

    body = {"products": [item], "payment_method": "balance", "auto_pay": True}
    invoice = client.post("/esims", json=body)

    if not invoice_settled(invoice):
        invoice = poll_invoice(client, invoice["id"])

    orders = invoice.get("orders") or []
    order = get_order(client, orders[0]["id"]) if orders else None
    redemption = (order or {}).get("redemption_info") or {}

    return {
        "invoice_id": invoice["id"],
        "invoice_status": invoice.get("status"),
        "order_status": (order or {}).get("status"),
        "is_topup": esim_id is not None,
        "barcode_value": redemption.get("barcode_value"),
        "instructions": redemption.get("instructions"),
    }


def remaining_data_gb(esim: dict[str, Any]) -> float:
    """Sum remaining_quantity (bytes) across active bundles -> GB."""
    total = sum(
        b.get("remaining_quantity", 0)
        for b in esim.get("package_history", [])
        if b.get("status") == "active"
    )
    return round(total / 1_073_741_824, 3)


if __name__ == "__main__":
    with BitrefillClient() as bf:
        products = list_esim_products(bf)
        print(f"{len(products)} eSIM products. First few:")
        for p in products[:5]:
            print(f"  {p['id']}: {p.get('name')}")
        if products:
            detail = get_esim_product(bf, products[0]["id"])
            pkgs = detail.get("packages", [])
            print(f"\n{detail['id']} packages:")
            for pk in pkgs[:6]:
                print(f"  {pk.get('value')}")
