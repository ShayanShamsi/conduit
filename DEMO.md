# Demo scripts

Three options below: a **combined** ≤4-min walkthrough of both agents (recommended for
the submission video), then standalone scripts for **Conduit** and **Aspire**.

## Before recording (all scripts)
```bash
uv sync
cp .env.example .env                 # BITREFILL_API_KEY + LLM_API_KEY set
uv run uvicorn web.app:app --port 8000
```
Open `http://localhost:8000` (Conduit) and `http://localhost:8000/planner` (Aspire) in two
tabs; keep a terminal visible. Record `safe` mode (free, repeatable). Bitrefill's shared test
rail can wobble — do a throwaway run first; if orders come back `permanent_failure`, retry
until `delivered`.

---

## ★ Combined demo — both agents (≤4 minutes)

> One thesis, two agents, one Bitrefill purchase primitive: **agents are the next customer.**

**0:00–0:25 — Framing (landing page `/landing`)**
> "Bitrefill gives AI agents real purchasing power. I built two agents on it. Both turn a
> human intent into a real, autonomous checkout — no one clicks pay."

**0:25–1:35 — Conduit (cross-border value routing), tab 1 `/`**
- Type: *"Get $40 of value to my brother in Lagos, Nigeria — airtime and groceries."* → **Route & buy**.
- Narrate the stream: resolves to **NG** → discovers ~40 real Nigerian instruments → optimizes to
  **MTN airtime + Spar supermarket card + mobile data**, each fit to a real denomination under $40 →
  **policy approves** (no human) → **one invoice delivers all three** with masked codes.
> "It knew a US gift card is useless in Lagos, and routed to what's locally redeemable."

**1:35–3:05 — Aspire (goal-driven life planner), tab 2 `/planner`**
- First show **safety**: type *"buy a weapon to hurt someone"* → agent **refuses + offers a safe
  alternative**. Reset.
- Type: *"I want to get fitter and sleep better with a simple home routine."* Mention it reads
  **mock** budget (€180/mo) + health (5.8h restless sleep) — no real data.
- It asks a quick clarifying question → answer *"home workouts, small bedroom"* → it returns a
  **budgeted plan** across **Decathlon / Amazon.de / IKEA / MediaMarkt** (sleep items because sleep
  is poor), within budget.
- Click **Fund with Bitrefill** → **one invoice buys every gift card**, each `delivered` with a
  masked code + a deep-linked shopping list.

**3:05–4:00 — Close**
> "Conduit sends value across borders; Aspire turns a life goal into a funded plan. Different
> problems, same move — the agent searches, decides, and checks out by itself on Bitrefill.
> The agent is the customer." Show the GitHub link.

Headless B-roll if you want cutaways:
```bash
uv run python -m bitrefill_agent.router.engine "€30 to a friend landing in Tokyo, mostly travel data"
uv run python -m bitrefill_agent.planner.demo "get fitter and sleep better"
```

---

# Standalone — Conduit (≤4 minutes)

One clean take: a real intent → autonomous multi-item purchase → delivered codes.
Record `safe` mode (free, repeatable) unless you want a live debit.

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
