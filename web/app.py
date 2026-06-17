"""Conduit web app — type an intent, watch the agent route and check out live.

POST /api/route streams Server-Sent Events for each stage (intent, discover,
optimize, approved/declined, execute). The frontend renders them as they arrive.
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from bitrefill_agent.client import BitrefillClient
from bitrefill_agent.planner.converse import next_turn
from bitrefill_agent.planner.fund import fund_plan
from bitrefill_agent.planner.profile import from_dicts, load_samples
from bitrefill_agent.router.engine import run_route
from bitrefill_agent.router.policy import SpendPolicy

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Conduit + Aspire", description="Agentic purchasing on Bitrefill")


class RouteIn(BaseModel):
    intent: str
    mode: str = "safe"            # "safe" (free test product) | "live" (spends credit)
    max_per_route: float = 60.0


class ChatIn(BaseModel):
    history: list[dict[str, str]]
    finance: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    use_samples: bool = True


class FundIn(BaseModel):
    plan: dict[str, Any]
    mode: str = "safe"


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "app.html")


@app.get("/planner")
def planner_page() -> FileResponse:
    return FileResponse(STATIC / "planner.html")


@app.get("/landing")
def landing() -> FileResponse:
    return FileResponse(STATIC / "landing.html")


@app.post("/api/route")
def route(body: RouteIn) -> StreamingResponse:
    events: "queue.Queue[dict[str, Any] | None]" = queue.Queue()

    def emit(stage: str, data: dict[str, Any]) -> None:
        events.put({"stage": stage, "data": data})

    def worker() -> None:
        try:
            result = run_route(
                body.intent,
                mode=body.mode,
                policy=SpendPolicy(max_per_route=body.max_per_route),
                emit=emit,
            )
            events.put({"stage": "result", "data": result})
        except Exception as e:  # surface failures to the client instead of hanging
            events.put({"stage": "error", "data": {"message": str(e)}})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = events.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# --- Aspire: goal-driven life planner ---------------------------------------
@app.post("/api/plan/chat")
def plan_chat(body: ChatIn) -> dict[str, Any]:
    """One conversational turn: clarify | refuse | plan."""
    profile = load_samples() if body.use_samples and not (body.finance or body.health) \
        else from_dicts(body.finance, body.health)
    turn = next_turn(body.history, profile)
    return {
        "type": turn.type,
        "message": turn.message,
        "questions": turn.questions,
        "plan": turn.plan,
        "profile": profile.summary(),
    }


@app.post("/api/plan/fund")
def plan_fund(body: FundIn) -> StreamingResponse:
    """Autonomously buy the plan's funding gift cards; stream progress as SSE."""
    events: "queue.Queue[dict[str, Any] | None]" = queue.Queue()

    def worker() -> None:
        try:
            events.put({"stage": "funding", "data": {"message": "creating one invoice for all gift cards…"}})
            with BitrefillClient() as client:
                result = fund_plan(client, body.plan, mode=body.mode)
            events.put({"stage": "funded", "data": {
                "mode": result.mode,
                "invoice_id": result.invoice_id,
                "all_delivered": result.all_delivered,
                "notes": result.notes,
                "cards": [
                    {"retailer": c.retailer_name, "denomination_eur": c.denomination_eur,
                     "status": c.status, "code": c.masked_code, "shopping_list": c.shopping_list}
                    for c in result.cards
                ],
            }})
        except Exception as e:
            events.put({"stage": "error", "data": {"message": str(e)}})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = events.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# Serve any other static assets (favicon, etc.)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
