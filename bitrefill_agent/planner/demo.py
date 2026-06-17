"""Headless Aspire demo — goal -> safety -> plan -> autonomous funding.

    uv run python -m bitrefill_agent.planner.demo "get fitter and sleep better"
    uv run python -m bitrefill_agent.planner.demo "..." --live

Uses the bundled mock finance + health samples.
"""

from __future__ import annotations

import sys

from ..client import BitrefillClient
from .converse import next_turn
from .fund import fund_plan
from .profile import load_samples


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--live"]
    mode = "live" if "--live" in sys.argv else "safe"
    goal = " ".join(args) or "Get fitter and sleep better with a simple home routine"

    profile = load_samples()
    print(f"› {goal}\n  signals: {profile.summary()}\n")

    with BitrefillClient() as bf:
        # Skip the clarifying round for a one-shot demo by giving two user turns.
        history = [
            {"role": "user", "content": goal},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "Use sensible defaults; just plan it."},
        ]
        turn = next_turn(history, profile, client=bf)
        if turn.type == "refuse":
            print("🛑 refused:", turn.message)
            return
        if turn.type != "plan" or not turn.plan:
            print("…", turn.message, turn.questions)
            return

        p = turn.plan
        print("PLAN:")
        for i in p["items"]:
            print(f"  • {i['name']}  [{i['retailer_name']}]  €{i['est_price_eur']}  — {i['why']}")
        print(f"  planned €{p['items_total']} / budget €{p['budget_eur']} "
              f"(within={p['within_budget']}); gift cards €{p['funding_total']} "
              f"(+€{p['surplus_eur']} kept as balance)")
        for n in p["notes"]:
            print(f"  note: {n}")

        print(f"\nFUNDING ({mode}, autonomous — one invoice):")
        result = fund_plan(bf, p, mode=mode)
        for c in result.cards:
            print(f"  ✓ {c.retailer_name} €{c.denomination_eur} → {c.status}  code {c.masked_code}")
        print(f"  invoice {result.invoice_id} | all_delivered {result.all_delivered}")
        for n in result.notes:
            print(f"  note: {n}")


if __name__ == "__main__":
    main()
