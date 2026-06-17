"""Milestone 5 — tool definitions mapping the Claude API to our functions.

Each TOOL_SCHEMAS entry is an Anthropic tool spec; TOOL_IMPLS dispatches a
tool name + input to the matching pipeline function. `create_and_pay_invoice`
is gated behind human approval in agent.py — it is the only money-spending tool.
"""

from __future__ import annotations

from typing import Any

from .catalog import describe_denominations, get_product, search_products
from .client import BitrefillClient
from .purchase import buy, summarize

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_products",
        "description": "Search the Bitrefill catalog by keyword. Returns product ids and names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword, e.g. 'amazon'"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_product_details",
        "description": "Get a product's available denominations (fixed packages and/or a value range).",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "create_and_pay_invoice",
        "description": (
            "Purchase a product, paying from account balance. Provide EITHER "
            "package_id (fixed denomination) OR value (range product). "
            "This SPENDS money and requires user approval."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "package_id": {"type": "string"},
                "value": {"type": "number"},
                "quantity": {"type": "integer", "default": 1},
                "phone_number": {"type": "string", "description": "E.164, for phone top-ups only"},
            },
            "required": ["product_id"],
        },
    },
]

# Names that spend money — agent.py asks the user before running these.
GATED_TOOLS = {"create_and_pay_invoice"}


def run_tool(client: BitrefillClient, name: str, args: dict[str, Any]) -> str:
    """Execute a tool by name and return a string result for the model."""
    if name == "search_products":
        results = search_products(client, args["query"], limit=args.get("limit", 5))
        return "\n".join(
            f"{p['id']}: {p.get('name')} ({p.get('country')})" for p in results
        ) or "no products found"

    if name == "get_product_details":
        product = get_product(client, args["product_id"])
        return f"{product['id']} ({product.get('name')}): {describe_denominations(product)}"

    if name == "create_and_pay_invoice":
        result = buy(
            client,
            args["product_id"],
            package_id=args.get("package_id"),
            value=args.get("value"),
            quantity=args.get("quantity", 1),
            phone_number=args.get("phone_number"),
        )
        return summarize(result)

    return f"unknown tool: {name}"
