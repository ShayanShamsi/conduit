"""Orchestrate the full route: intent -> discover -> optimize -> policy -> execute.

`run_route` emits progress events through a callback so the CLI and the web app
(SSE) can show each stage live. Returns a final result dict.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from ..client import BitrefillClient
from .discover import discover_instruments
from .execute import execute_basket
from .intent import parse_intent
from .optimize import optimize
from .policy import SpendPolicy

Emit = Callable[[str, dict[str, Any]], None]


def _noop(stage: str, data: dict[str, Any]) -> None:
    pass


def run_route(
    intent_text: str,
    *,
    mode: str = "safe",
    policy: SpendPolicy | None = None,
    emit: Emit = _noop,
    client: BitrefillClient | None = None,
) -> dict[str, Any]:
    policy = policy or SpendPolicy()
    own_client = client is None
    client = client or BitrefillClient()
    try:
        # 1. Intent
        req = parse_intent(intent_text)
        emit("intent", asdict(req))

        # Country policy gate
        reason = policy.check_country(req.country)
        if reason:
            emit("declined", {"reason": reason})
            return {"status": "declined", "reason": reason, "request": asdict(req)}

        # 2. Discover
        instruments = discover_instruments(client, req)
        emit("discover", {
            "country": req.country,
            "count": len(instruments),
            "instruments": [
                {"product_id": i.product_id, "name": i.name, "kind": i.kind,
                 "currency": i.currency, "min_cost": round(i.min_cost, 2)}
                for i in instruments
            ],
        })
        if not instruments:
            emit("declined", {"reason": f"no instruments found for {req.country}"})
            return {"status": "declined", "reason": "no_instruments", "request": asdict(req)}

        # 3. Optimize
        basket = optimize(req, instruments, policy)
        emit("optimize", {
            "lines": [asdict_line(ln) for ln in basket.lines],
            "total_cost": basket.total_cost,
            "leftover": basket.leftover,
            "notes": basket.notes,
        })
        if not basket.lines:
            emit("declined", {"reason": "could not assemble a basket"})
            return {"status": "declined", "reason": "empty_basket", "request": asdict(req)}

        # 4. Policy gate (the autonomy decision — replaces human approval)
        reason = policy.check_basket(basket.total_cost, [ln.cost for ln in basket.lines])
        if reason:
            emit("declined", {"reason": reason})
            return {"status": "declined", "reason": reason,
                    "request": asdict(req), "basket": [asdict_line(l) for l in basket.lines]}
        emit("approved", {
            "total_cost": basket.total_cost,
            "policy": {"max_per_route": policy.max_per_route,
                       "max_per_order": policy.max_per_order,
                       "allowed_countries": sorted(policy.allowed_countries)
                       if policy.allowed_countries else None},
        })

        # 5. Execute autonomously
        fulfillment = execute_basket(client, basket, mode=mode)
        emit("execute", _fulfillment_dict(fulfillment))

        return {
            "status": "fulfilled" if fulfillment.all_delivered else "partial",
            "request": asdict(req),
            "basket": [asdict_line(l) for l in basket.lines],
            "fulfillment": _fulfillment_dict(fulfillment),
        }
    finally:
        if own_client:
            client.close()


# --- small serialization helpers (avoid leaking secrets, keep payloads flat) --
def asdict_line(ln) -> dict[str, Any]:
    return {
        "name": ln.name, "kind": ln.kind, "face": f"{ln.face_label} {ln.currency}".strip(),
        "cost": ln.cost, "why": ln.why,
    }


def _fulfillment_dict(f) -> dict[str, Any]:
    return {
        "mode": f.mode,
        "invoice_id": f.invoice_id,
        "invoice_status": f.invoice_status,
        "all_delivered": f.all_delivered,
        "notes": f.notes,
        "lines": [
            {"name": l.name, "kind": l.kind, "face": l.face_label,
             "status": l.status, "code": l.masked_code, "why": l.why}
            for l in f.lines
        ],
    }


if __name__ == "__main__":
    import sys

    def show(stage: str, data: dict[str, Any]) -> None:
        print(f"\n[{stage}]")
        if stage == "optimize":
            for ln in data["lines"]:
                print(f"  • {ln['name']} ({ln['kind']}) {ln['face']} — ${ln['cost']}  «{ln['why']}»")
            print(f"  total ${data['total_cost']} | leftover ${data['leftover']}")
        elif stage == "execute":
            for ln in data["lines"]:
                print(f"  ✓ {ln['name']}: {ln['status']} code={ln['code']}")
            print(f"  invoice {data['invoice_id']} delivered={data['all_delivered']}")
        else:
            print("  ", data)

    text = " ".join(sys.argv[1:]) or "Get $40 of value to my brother in Lagos, Nigeria — airtime and groceries."
    mode = "live" if "--live" in sys.argv else "safe"
    run_route(text.replace("--live", "").strip(), mode=mode, emit=show)
