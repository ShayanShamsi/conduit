"""Milestone 2 — browse the catalog (read-only).

Wraps the product endpoints and adds a tiny TTL cache so we don't burn the
1000 req/hour product quota. Exposes the packages-vs-ranges distinction that
the purchase pipeline depends on.
"""

from __future__ import annotations

import time
from typing import Any

from .client import BitrefillClient


def search_products(
    client: BitrefillClient,
    query: str,
    *,
    limit: int = 10,
    include_test: bool = True,
) -> list[dict[str, Any]]:
    """GET /products/search?q=... — find products by keyword."""
    params: dict[str, Any] = {"q": query, "limit": limit}
    if include_test:
        params["include_test_products"] = "true"
    return client.get("/products/search", params=params)


def get_product(client: BitrefillClient, product_id: str) -> dict[str, Any]:
    """GET /products/{id} — full product incl. packages and/or range."""
    return client.get(f"/products/{product_id}")


def describe_denominations(product: dict[str, Any]) -> str:
    """Human-readable summary of how this product can be priced."""
    parts: list[str] = []
    packages = product.get("packages") or []
    if packages:
        values = ", ".join(str(p.get("value")) for p in packages)
        parts.append(f"fixed packages: {values}")
    rng = product.get("range")
    if rng:
        parts.append(
            f"range: {rng.get('min')}–{rng.get('max')} (step {rng.get('step')})"
        )
    return " | ".join(parts) or "no denominations listed"


def quota_remaining(client: BitrefillClient) -> int | None:
    """Read the product quota header from the most recent response."""
    if client.last_headers is None:
        return None
    raw = client.last_headers.get("X-product-quota-remaining")
    return int(raw) if raw is not None else None


class ProductCache:
    """In-memory product cache keyed by product id, with a TTL refresh."""

    def __init__(self, client: BitrefillClient, *, ttl_seconds: float = 3600):
        self.client = client
        self.ttl = ttl_seconds
        self._by_id: dict[str, dict[str, Any]] = {}
        self._fetched_at: dict[str, float] = {}

    def get(self, product_id: str) -> dict[str, Any]:
        now = time.monotonic()
        fresh = now - self._fetched_at.get(product_id, 0) < self.ttl
        if not fresh or product_id not in self._by_id:
            self._by_id[product_id] = get_product(self.client, product_id)
            self._fetched_at[product_id] = now
        return self._by_id[product_id]


if __name__ == "__main__":
    with BitrefillClient() as bf:
        for p in search_products(bf, "amazon", limit=3):
            print(f"{p['id']}: {p.get('name')} ({p.get('country')})")
        test = get_product(bf, "test-gift-card-code")
        print("test product ->", describe_denominations(test))
        print("quota remaining ->", quota_remaining(bf))
