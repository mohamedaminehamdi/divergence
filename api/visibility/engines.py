"""One interface over four grounded answer engines.

Every engine runs in its web-search/grounding mode. Without that they answer from
training data, which tells you nothing about whether you are cited *today* — the
only question this product asks.

Raw HTTP rather than four vendor SDKs: each call is one POST and one parse.
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

TIMEOUT = httpx.Timeout(90.0, connect=10.0)
MAX_CONCURRENCY = 8


@dataclass
class EngineResponse:
    engine: str
    prompt: str
    answer: str = ""
    citations: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def cited_domains(self) -> set[str]:
        out = set()
        for c in self.citations:
            host = urlparse(c).netloc.removeprefix("www.").lower()
            if host:
                out.add(host)
        return out


class Engine:
    name: str
    env_key: str

    def configured(self) -> bool:
        return bool(os.getenv(self.env_key))

    async def ask(self, client: httpx.AsyncClient, prompt: str) -> EngineResponse:
        if not self.configured():
            return EngineResponse(self.name, prompt, error=f"{self.env_key} not set")
        try:
            resp = await self._call(client, prompt)
            resp.raise_for_status()
            return self._parse(prompt, resp.json())
        except httpx.HTTPStatusError as e:
            return EngineResponse(self.name, prompt, error=f"HTTP {e.response.status_code}: {e.response.text[:200]}")
        except (httpx.HTTPError, ValueError, KeyError) as e:
            return EngineResponse(self.name, prompt, error=f"{type(e).__name__}: {e}")

    async def _call(self, client, prompt): raise NotImplementedError
    def _parse(self, prompt, data) -> EngineResponse: raise NotImplementedError


class Perplexity(Engine):
    """Returns citation URLs natively — the strongest ground truth of the four."""

    name, env_key = "perplexity", "PERPLEXITY_API_KEY"

    async def _call(self, client, prompt):
        return await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {os.environ[self.env_key]}"},
            json={"model": "sonar", "messages": [{"role": "user", "content": prompt}]},
        )

    def _parse(self, prompt, data):
        answer = data["choices"][0]["message"]["content"]
        cites = data.get("citations") or [r.get("url", "") for r in data.get("search_results", [])]
        return EngineResponse(self.name, prompt, answer, [c for c in cites if c])


class OpenAI(Engine):
    name, env_key = "openai", "OPENAI_API_KEY"

    async def _call(self, client, prompt):
        return await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {os.environ[self.env_key]}"},
            json={"model": "gpt-5", "input": prompt, "tools": [{"type": "web_search"}]},
        )

    def _parse(self, prompt, data):
        answer, cites = "", []
        for item in data.get("output", []):
            for block in item.get("content", []) if isinstance(item, dict) else []:
                if block.get("type") == "output_text":
                    answer += block.get("text", "")
                    for ann in block.get("annotations", []):
                        if ann.get("type") == "url_citation" and ann.get("url"):
                            cites.append(ann["url"])
        return EngineResponse(self.name, prompt, answer, cites)


class Anthropic(Engine):
    name, env_key = "anthropic", "ANTHROPIC_API_KEY"

    async def _call(self, client, prompt):
        return await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": os.environ[self.env_key], "anthropic-version": "2023-06-01"},
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            },
        )

    def _parse(self, prompt, data):
        answer, cites = "", []
        for block in data.get("content", []):
            if block.get("type") == "text":
                answer += block.get("text", "")
                for c in block.get("citations") or []:
                    if c.get("url"):
                        cites.append(c["url"])
            elif block.get("type") == "web_search_tool_result":
                for r in block.get("content", []) if isinstance(block.get("content"), list) else []:
                    if isinstance(r, dict) and r.get("url"):
                        cites.append(r["url"])
        return EngineResponse(self.name, prompt, answer, cites)


class Gemini(Engine):
    """Closest available proxy for AI Overviews behaviour."""

    name, env_key = "gemini", "GEMINI_API_KEY"

    async def _call(self, client, prompt):
        return await client.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            headers={"x-goog-api-key": os.environ[self.env_key]},
            json={"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]},
        )

    def _parse(self, prompt, data):
        cand = (data.get("candidates") or [{}])[0]
        answer = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        cites = []
        for chunk in cand.get("groundingMetadata", {}).get("groundingChunks", []):
            web = chunk.get("web", {})
            # uri is a vertexaisearch redirect; title carries the real domain.
            if web.get("title"):
                cites.append(f"https://{web['title']}" if "." in web["title"] and " " not in web["title"] else web.get("uri", ""))
            elif web.get("uri"):
                cites.append(web["uri"])
        return EngineResponse(self.name, prompt, answer, [c for c in cites if c])


ENGINES = [Perplexity(), OpenAI(), Anthropic(), Gemini()]


def configured_engines() -> list[Engine]:
    return [e for e in ENGINES if e.configured()]


async def run_matrix(prompts: list[str], engines: list[Engine] | None = None) -> list[EngineResponse]:
    """Every engine x every prompt, bounded concurrency."""
    engines = engines if engines is not None else configured_engines()
    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async def one(engine: Engine, prompt: str) -> EngineResponse:
            async with sem:
                return await engine.ask(client, prompt)

        return list(await asyncio.gather(*(one(e, p) for e in engines for p in prompts)))
