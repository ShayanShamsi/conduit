"""Spend policy — what makes the agent autonomous instead of asking a human.

Instead of an interactive "approve this purchase?" gate, every route is checked
against a policy. If it passes, the agent executes with zero humans in the loop;
if it fails, it declines and explains why.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpendPolicy:
    max_per_route: float = 60.0          # total settlement cost cap per intent
    max_per_order: float = 40.0          # cap on any single line
    allowed_countries: set[str] | None = None   # None = any
    blocked_kinds: set[str] = field(default_factory=set)

    def check_country(self, country: str) -> str | None:
        if self.allowed_countries and country not in self.allowed_countries:
            return f"country {country} is not in the allowed list"
        return None

    def check_basket(self, total_cost: float, line_costs: list[float]) -> str | None:
        """Return None if the basket is allowed, else a human-readable reason."""
        if total_cost > self.max_per_route + 1e-6:
            return f"total ${total_cost:.2f} exceeds per-route cap ${self.max_per_route:.2f}"
        for c in line_costs:
            if c > self.max_per_order + 1e-6:
                return f"a line costs ${c:.2f}, over per-order cap ${self.max_per_order:.2f}"
        return None
