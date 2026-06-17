"""Milestone 5 — the LLM tool-calling loop (the agent's brain).

Uses any OpenAI-compatible chat-completions provider so you can run it on a free
model (default: OpenRouter free tier). Configure via .env:
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

Classic tool-use loop: model -> tool_calls -> we execute -> tool results -> repeat.
Money-spending tools are gated behind an interactive approval prompt.
"""

from __future__ import annotations

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from .client import BitrefillClient
from .tools import GATED_TOOLS, TOOL_SCHEMAS, run_tool

load_dotenv()

SYSTEM = (
    "You are a Bitrefill purchasing agent. You can search the catalog, inspect "
    "product denominations, and buy products paid from the user's account balance. "
    "Before buying, always inspect the product's denominations and pick a valid one. "
    "During development, prefer test products (ids starting with 'test-'). "
    "Never invent product ids or package ids — look them up. Keep responses concise."
)


def _openai_tools() -> list[dict]:
    """Convert our Anthropic-style schemas to OpenAI function-tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in TOOL_SCHEMAS
    ]


def approve(tool_name: str, tool_input: dict, *, auto: bool) -> bool:
    """Human-in-the-loop gate for money-spending tools."""
    if tool_name not in GATED_TOOLS:
        return True
    print(f"\n🔐 Approval needed: {tool_name}({tool_input})")
    if auto:
        print("   auto-approve enabled -> yes")
        return True
    return input("   Approve this purchase? [y/N] ").strip().lower() in {"y", "yes"}


def run_agent(prompt: str, *, auto_approve: bool = False, max_turns: int = 10) -> str:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing LLM_API_KEY. Get a free key (e.g. openrouter.ai/keys) and set "
            "LLM_API_KEY / LLM_BASE_URL / LLM_MODEL in .env."
        )
    llm = OpenAI(api_key=api_key, base_url=os.environ.get("LLM_BASE_URL"))
    model = os.environ.get("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    tools = _openai_tools()

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ]

    with BitrefillClient() as client:
        for _ in range(max_turns):
            response = llm.chat.completions.create(
                model=model, messages=messages, tools=tools, max_tokens=1024
            )
            msg = response.choices[0].message

            if not msg.tool_calls:
                return (msg.content or "").strip()

            # Echo the assistant turn (with its tool calls) back into the history.
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
                }
            )

            for call in msg.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                if not approve(name, args, auto=auto_approve):
                    out = "Purchase declined by the user."
                else:
                    try:
                        out = run_tool(client, name, args)
                    except Exception as e:  # surface API errors back to the model
                        out = f"tool error: {e}"
                print(f"   ↳ {name} -> {out}")
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": out}
                )

    return "Reached max turns without a final answer."


if __name__ == "__main__":
    user_prompt = " ".join(sys.argv[1:]) or "Find a test gift card and buy a $10 one."
    auto = os.environ.get("AGENT_AUTO_APPROVE") == "1"
    print(f"› {user_prompt}\n")
    print("=== agent ===")
    print(run_agent(user_prompt, auto_approve=auto))
