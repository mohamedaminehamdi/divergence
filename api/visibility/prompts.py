"""Infer what buyers would actually ask an assistant about this site."""
from __future__ import annotations

import json
import os
import re

import httpx

DEFAULT_COUNT = 8

SYSTEM = """You write the questions a potential buyer would type into ChatGPT or Perplexity \
when they are looking for a product like the one on this page, BEFORE they know the brand exists.

Rules:
- Never name the brand. The whole point is to test whether the engine surfaces it unprompted.
- Write the way people actually type: "best X for Y", "how do I ...", "X vs alternatives".
- Cover a mix: category discovery, comparison, pricing, and a specific problem the product solves.
- Each question must stand alone.

Return ONLY JSON: {"category": "<short category>", "prompts": ["...", "..."]}"""


async def generate(brand: str, page_text: str, count: int = DEFAULT_COUNT) -> tuple[str, list[str]]:
    """Return (category, prompts). Falls back to templates without an API key."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return _fallback(brand)

    excerpt = page_text[:6000]
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1000,
        "system": SYSTEM,
        "messages": [
            {
                "role": "user",
                "content": f"Brand: {brand}\n\nPage content:\n{excerpt}\n\nWrite {count} questions.",
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                json=payload,
            )
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", []))
        data = json.loads(re.search(r"\{.*\}", text, re.S).group())
        prompts = [p.strip() for p in data.get("prompts", []) if isinstance(p, str) and p.strip()]
        if not prompts:
            return _fallback(brand)
        return data.get("category", "").strip() or "this category", prompts[:count]
    except (httpx.HTTPError, ValueError, AttributeError, KeyError):
        return _fallback(brand)


def _fallback(brand: str) -> tuple[str, list[str]]:
    """Templated prompts so the flow still works without a key. Deliberately generic —
    the UI presents these as editable, and a wrong guess is cheap to correct."""
    return (
        "this category",
        [
            f"What is {brand} and what does it do?",
            f"Is {brand} any good?",
            f"How much does {brand} cost?",
            f"What are the best alternatives to {brand}?",
            f"{brand} vs its competitors: which should I choose?",
            f"What do reviews say about {brand}?",
            f"Who should use {brand}?",
            f"Is {brand} worth it for a small team?",
        ],
    )
