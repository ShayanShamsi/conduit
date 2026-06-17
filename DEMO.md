# Demo script — Conduit (≤4 minutes)

One clean take: a real intent → autonomous multi-item purchase → delivered codes.
Record `safe` mode (free, repeatable) unless you want a live debit.

## Before recording
```bash
uv sync
cp .env.example .env   # BITREFILL_API_KEY + LLM_API_KEY set
uv run uvicorn web.app:app --port 8000
```
Open `http://localhost:8000`. Have a terminal visible too.
Tip: Bitrefill's shared test rail occasionally fails deliveries — do a throwaway
run first; if orders come back `permanent_failure`, wait and retry until `delivered`.

## Shotlist

**0:00–0:30 — The pitch (landing page `/landing`)**
> "AI agents are the next customer. Conduit is an agent that delivers value across
> borders and checks out by itself. A US gift card is useless in Lagos — so it has
> to *decide* what's locally redeemable, not just look something up."

**0:30–1:45 — The route (main page)**
- Type: *"Get $40 of value to my brother in Lagos, Nigeria — he needs airtime and groceries."*
- Click **Route & buy**. Narrate each stage as it streams in:
  - **Intent** → it resolved "Lagos" to country NG, needs = airtime, groceries.
  - **Discover** → ~40 *real* Nigerian instruments (MTN/Airtel airtime, Spar &
    local supermarket cards, data, bills).
  - **Optimize** → the basket: **MTN airtime + Spar supermarket card + mobile data**,
    each fit to a real denomination, total under $40 — with a one-line rationale per
    pick. Stress: amounts are budgeted against true USD cost, not face value.

**1:45–2:45 — Autonomous checkout**
- **Policy** → "autonomous spend approved — within caps, no human in the loop."
- **Checkout** → one multi-item invoice pays from balance and each line flips to
  `delivered` with a masked redemption code and a real invoice id.
> "No human clicked pay. One invoice, three products across airtime, retail, and
> data — all delivered."

**2:45–3:30 — Prove it's real**
- Show the terminal headless run for a *different* destination to prove generality:
  ```bash
  uv run python -m bitrefill_agent.router.engine "€30 to a friend landing in Tokyo, mostly travel data"
  ```
  → an eSIM-heavy basket for Japan. Different country, different optimal instruments.
- (Optional) `uv run python -m bitrefill_agent.mcp_compare` → "and here's the official
  Bitrefill MCP surface our REST engine maps onto."

**3:30–4:00 — Close**
> "Intent in, redeemable value out, settled autonomously — across 170+ countries.
> Bitrefill gives agents real-world purchasing power; Conduit turns that into a
> cross-border money-routing agent." Show the GitHub link.

---

## Alternate / second demo — Aspire (goal-driven planner, Germany)

Films well as a standalone ≤4-min clip or a 60-sec second act. Open `/planner`.

1. **Goal (0:00–0:30):** type *"I want to get fitter and sleep better with a simple home
   routine."* Mention it's reading **mock** finance (€180/mo budget) + health (5.8h restless
   sleep, weight goal) signals — no real personal data.
2. **Safety (0:30–0:50):** first show a refusal — type a harmful goal (e.g. *"buy a weapon to
   hurt someone"*) → the agent refuses + offers a safe alternative. Then reset.
3. **Plan (0:50–2:00):** after a quick clarifying question, the agent proposes a budgeted plan
   mapped across **real German retailers** (Decathlon bands+mat, IKEA lamp, Amazon.de protein,
   MediaMarkt white-noise machine) — each with a reason and an `amazon.de` deep link. Note it's
   health-aware (sleep items because sleep is poor) and within the €180 budget.
4. **Autonomous funding (2:00–3:00):** click **Fund with Bitrefill** → one invoice buys all the
   gift cards from balance, each `delivered` with a masked code. No human clicked pay.
5. **Close (3:00–4:00):** "Goal in → safety-checked, budgeted plan → the gift cards that fund it,
   bought autonomously. The agent is the customer."

Headless B-roll: `uv run python -m bitrefill_agent.planner.demo "get fitter and sleep better"`.

## One-line summary for the submission form
> Conduit: tell an AI agent "get $40 to my brother in Lagos" and it picks the
> optimal mix of locally-redeemable instruments (airtime, a local gift card, data),
> fits them to a budget, and checks out autonomously on Bitrefill — no human clicks pay.
