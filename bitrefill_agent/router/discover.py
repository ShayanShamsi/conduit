"""Discover candidate instruments for a destination country.

Deterministic catalog queries (no LLM): pull the country's products, classify
each into a routing 'kind', and capture its denominations with REAL settlement
cost (`price`) alongside the local face `value`. Cost is what we budget against;
face value is what the recipient sees.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..catalog import get_product
from ..client import BitrefillClient
from ..esim import list_esim_products
from .intent import RouteRequest

# kind -> base usefulness for someone receiving value locally (0..1).
KIND_BASE_SCORE = {
    "airtime": 0.9,
    "mobile_data": 0.85,
    "esim": 0.8,
    "giftcard": 0.7,
    "bill": 0.6,
}


@dataclass
class Denom:
    package_id: str       # full id, e.g. "airtel-nigeria<&>5000"
    face_value: float     # local-currency amount (0 for non-numeric, e.g. eSIM)
    cost: float           # settlement-currency cost (USD/EUR), from `price`
    label: str = ""       # display label, e.g. "5000" or "3GB, 30 Days"

    def __post_init__(self) -> None:
        if not self.label:
            self.label = f"{self.face_value:g}"


@dataclass
class Instrument:
    product_id: str
    name: str
    kind: str
    currency: str         # local face currency (NGN, JPY, USD…)
    recipient_type: str
    denoms: list[Denom] = field(default_factory=list)
    range_min: float | None = None
    range_max: float | None = None
    range_step: float | None = None
    range_rate: float | None = None   # cost = face_value * range_rate
    score: float = 0.0

    @property
    def min_cost(self) -> float:
        costs = [d.cost for d in self.denoms]
        if self.range_rate and self.range_min is not None:
            costs.append(self.range_min * self.range_rate)
        return min(costs) if costs else float("inf")

    def cost_of(self, face_value: float) -> float | None:
        if self.range_rate is not None:
            return round(face_value * self.range_rate, 2)
        for d in self.denoms:
            if abs(d.face_value - face_value) < 1e-9:
                return d.cost
        return None


def _classify(product: dict[str, Any]) -> str:
    rid = product.get("id", "")
    name = (product.get("name") or "").lower()
    rtype = product.get("recipient_type")
    if "esim" in rid or "esim" in name:
        return "esim"
    if rtype == "account":
        return "bill"
    if rtype == "phone_number":
        return "mobile_data" if ("data" in rid or "data" in name) else "airtime"
    return "giftcard"


def _denoms(product: dict[str, Any]) -> list[Denom]:
    out: list[Denom] = []
    for p in product.get("packages") or []:
        if "id" not in p:
            continue
        label = str(p.get("value", ""))
        try:
            face = float(p["value"])
        except (ValueError, TypeError):
            face = 0.0  # non-numeric (eSIM "3GB, 30 Days")
        if p.get("price") is None and face == 0.0:
            continue  # no cost signal and no face value -> unusable
        cost = float(p.get("price", face))
        out.append(Denom(p["id"], face, cost, label))
    return out


def _to_instrument(product: dict[str, Any]) -> Instrument:
    rng = product.get("range") or {}
    inst = Instrument(
        product_id=product["id"],
        name=product.get("name", product["id"]),
        kind=_classify(product),
        currency=product.get("currency", ""),
        recipient_type=product.get("recipient_type", "none"),
        denoms=_denoms(product),
        range_min=rng.get("min"),
        range_max=rng.get("max"),
        range_step=rng.get("step"),
        range_rate=rng.get("price_rate"),
    )
    inst.score = KIND_BASE_SCORE.get(inst.kind, 0.5)
    return inst


def discover_instruments(
    client: BitrefillClient, req: RouteRequest, *, limit: int = 40
) -> list[Instrument]:
    """Return in-stock, purchasable instruments for the destination country."""
    raw = client.get(
        "/products", params={"country": req.country, "limit": limit}
    )
    instruments: list[Instrument] = []
    seen: set[str] = set()
    for p in raw:
        if not p.get("in_stock", True) or p["id"] in seen:
            continue
        inst = _to_instrument(p)
        # Need at least one buyable denomination (fixed or range).
        if inst.denoms or inst.range_rate is not None:
            instruments.append(inst)
            seen.add(p["id"])

    # Add an eSIM covering the country (great for "just landed" / travel needs).
    esim = _find_esim_for_country(client, req.country)
    if esim is not None and esim.product_id not in seen:
        instruments.append(esim)
        seen.add(esim.product_id)

    return instruments


def _find_esim_for_country(client: BitrefillClient, country: str) -> Instrument | None:
    """Find one eSIM whose coverage includes the destination (exact ISO match)."""
    country = country.upper()
    for ep in list_esim_products(client):
        codes = {str(ep.get("country_code", "")).upper()}
        codes |= {str(c).upper() for c in (ep.get("coverage") or [])}
        if country in codes:
            try:
                full = get_product_esim(client, ep["id"])
                inst = _to_instrument({**full, "recipient_type": "mixed"})
                inst.kind = "esim"
                inst.score = KIND_BASE_SCORE["esim"]
                if inst.denoms or inst.range_rate is not None:
                    return inst
            except Exception:
                return None
    return None


def get_product_esim(client: BitrefillClient, esim_id: str) -> dict[str, Any]:
    return client.get(f"/products/esims/{esim_id}")
