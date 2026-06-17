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

from bitrefill_agent.router.engine import run_route
from bitrefill_agent.router.policy import SpendPolicy

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="Conduit", description="Cross-border value-routing agent")


class RouteIn(BaseModel):
    intent: str
    mode: str = "safe"            # "safe" (free test product) | "live" (spends credit)
    max_per_route: float = 60.0


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "app.html")


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


# Serve any other static assets (favicon, etc.)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
