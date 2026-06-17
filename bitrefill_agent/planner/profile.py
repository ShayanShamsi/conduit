"""Load mock finance + health signals into a compact Profile.

Files are MOCK (see data/*.json) — no real personal data. A user can also pass
already-parsed dicts (e.g. from an upload), which we coerce to the same shape.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@dataclass
class Profile:
    currency: str = "EUR"
    monthly_discretionary: float = 150.0
    savings_goal_monthly: float = 0.0
    fixed_costs: dict[str, float] = field(default_factory=dict)
    # health signals (all optional)
    sleep_hours: float | None = None
    sleep_quality: str = ""
    steps_avg: int | None = None
    resting_hr: int | None = None
    weight_kg: float | None = None
    goal_weight_kg: float | None = None
    activity_level: str = ""
    dietary: str = ""
    notes: str = ""

    def summary(self) -> str:
        """A compact, LLM-friendly description of the signals."""
        bits = [f"budget {self.currency} {self.monthly_discretionary:.0f}/month discretionary"]
        if self.savings_goal_monthly:
            bits.append(f"savings goal {self.currency} {self.savings_goal_monthly:.0f}/mo")
        if self.sleep_hours:
            bits.append(f"sleep {self.sleep_hours}h ({self.sleep_quality})".strip())
        if self.steps_avg:
            bits.append(f"{self.steps_avg} steps/day")
        if self.weight_kg and self.goal_weight_kg:
            bits.append(f"weight {self.weight_kg}->{self.goal_weight_kg} kg")
        if self.activity_level:
            bits.append(self.activity_level)
        if self.dietary:
            bits.append(f"diet: {self.dietary}")
        return "; ".join(bits)


def from_dicts(finance: dict[str, Any] | None, health: dict[str, Any] | None) -> Profile:
    finance = finance or {}
    health = health or {}
    return Profile(
        currency=finance.get("currency", "EUR"),
        monthly_discretionary=float(finance.get("monthly_discretionary", 150)),
        savings_goal_monthly=float(finance.get("savings_goal_monthly", 0)),
        fixed_costs=finance.get("fixed_costs", {}) or {},
        sleep_hours=health.get("sleep_avg_hours"),
        sleep_quality=health.get("sleep_quality", ""),
        steps_avg=health.get("steps_avg_daily"),
        resting_hr=health.get("resting_heart_rate"),
        weight_kg=health.get("weight_kg"),
        goal_weight_kg=health.get("goal_weight_kg"),
        activity_level=health.get("activity_level", ""),
        dietary=health.get("dietary", ""),
        notes=" ".join(filter(None, [finance.get("risk_notes", ""), health.get("goals_free_text", "")])),
    )


def load_samples() -> Profile:
    """Load the bundled mock finance + health files."""
    def _read(name: str) -> dict[str, Any]:
        p = DATA_DIR / name
        return json.loads(p.read_text()) if p.exists() else {}

    return from_dicts(_read("mock_finances.json"), _read("mock_health.json"))
