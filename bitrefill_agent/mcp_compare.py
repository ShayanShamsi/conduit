"""Milestone 7 — compare our hand-built agent surface to the hosted MCP server.

The hosted server lives at https://api.bitrefill.com/mcp and exposes 7 tools.
For programmatic access (no browser/OAuth) you can authenticate by putting your
API key in the path: https://api.bitrefill.com/mcp/YOUR_API_KEY

This module connects with the MCP streamable-HTTP client and lists the live
tools, then prints how they map to what we built on the raw REST API.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

from .tools import TOOL_SCHEMAS

load_dotenv()

MCP_BASE = "https://api.bitrefill.com/mcp"

# How the 7 official MCP tools relate to our hand-built REST functions.
MAPPING = {
    "search-products": "catalog.search_products",
    "get-product-details": "catalog.get_product (+ describe_denominations)",
    "buy-products": "purchase.buy / extras.gift / esim.buy_esim (we split by type)",
    "submit-prepayment-step": "(not built — bill-payment form chains)",
    "list-invoices": "(not built — GET /invoices list)",
    "get-invoice-by-id": "purchase.poll_invoice / GET /invoices/{id}",
    "update-order": "(not built — track balance / archive)",
}

# Notable differences worth knowing (from the docs).
DIFFERENCES = [
    "Responses are TOON-formatted (not JSON); buy-products returns an "
    "`agent_instructions` field to steer the agent's next step.",
    "package_id in buy-products is the bare value ('50'), not the full "
    "'amazon_com-usa<&>50' id our REST calls use.",
    "One buy-products tool covers gift cards, eSIMs, refills AND gifting "
    "(gift object: theme/send_date) — we split these across modules.",
    "Prepayment step-chains (submit-prepayment-step) handle prepaid Visa / "
    "utility bills — no equivalent in our build.",
    "Payment options include x402 wallet flow and return_payment_link web "
    "checkout, beyond our balance-only path.",
]


async def list_live_tools(api_key: str) -> list[tuple[str, str]]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = f"{MCP_BASE}/{api_key}"
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            resp = await session.list_tools()
            return [(t.name, (t.description or "").split("\n")[0]) for t in resp.tools]


def print_comparison(live: list[tuple[str, str]] | None) -> None:
    print("Our hand-built tools (REST):")
    for t in TOOL_SCHEMAS:
        print(f"  - {t['name']}")

    print("\nHosted MCP tools", "(live):" if live else "(documented):")
    names = [n for n, _ in live] if live else list(MAPPING)
    for name in names:
        print(f"  - {name:24s} -> {MAPPING.get(name, '(new)')}")

    print("\nKey differences:")
    for d in DIFFERENCES:
        print(f"  • {d}")


def main() -> None:
    api_key = os.environ.get("BITREFILL_API_KEY")
    live = None
    if api_key:
        try:
            live = asyncio.run(list_live_tools(api_key))
        except Exception as e:
            print(f"(could not reach MCP server live: {e})\n")
    print_comparison(live)


if __name__ == "__main__":
    main()
