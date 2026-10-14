"""Turn raw engine answers into a visibility score.

Citation (your domain in the sources) counts for more than a mention (your name in
the prose): a mention can come from training recall, a citation means the engine
retrieved you today and chose to attribute.
"""
from __future__ import annotations

import re
from collections import Counter

from .engines import EngineResponse

CITED_POINTS = 1.0
MENTIONED_POINTS = 0.4


def _mention_offset(answer: str, brand: str) -> int | None:
    """Character offset of the first whole-word brand mention, or None."""
    if not brand.strip():
        return None
    m = re.search(rf"\b{re.escape(brand.strip())}\b", answer, re.I)
    return m.start() if m else None


def score_response(r: EngineResponse, brand: str, domain: str) -> dict:
    domain = domain.removeprefix("www.").lower()
    cited = any(d == domain or d.endswith(f".{domain}") for d in r.cited_domains)
    offset = _mention_offset(r.answer, brand)
    return {
        "engine": r.engine,
        "prompt": r.prompt,
        "error": r.error,
        "cited": cited,
        "mentioned": offset is not None,
        "first_mention_offset": offset,
        "answer_length": len(r.answer),
        "citation_count": len(r.citations),
        "answer_excerpt": _excerpt(r.answer, offset),
        "citations": r.citations[:10],
    }


def _excerpt(answer: str, offset: int | None, width: int = 260) -> str:
    if not answer:
        return ""
    if offset is None:
        return answer[:width].strip()
    start = max(0, offset - width // 3)
    return ("..." if start else "") + answer[start: start + width].strip() + "..."


def _points(s: dict) -> float:
    """A cited response scores full; a bare mention scores partial. Never both."""
    return CITED_POINTS if s["cited"] else MENTIONED_POINTS if s["mentioned"] else 0.0


def aggregate(responses: list[EngineResponse], brand: str, domain: str) -> dict:
    domain = domain.removeprefix("www.").lower()
    scored = [score_response(r, brand, domain) for r in responses]
    ok = [s for s in scored if not s["error"]]

    points = sum(_points(s) for s in ok)
    overall = round(100 * points / len(ok)) if ok else 0

    engines = {}
    for s in ok:
        e = engines.setdefault(s["engine"], {"engine": s["engine"], "cited": 0, "mentioned": 0, "total": 0, "points": 0.0})
        e["total"] += 1
        e["cited"] += s["cited"]
        e["mentioned"] += s["mentioned"]
        e["points"] += _points(s)
    for e in engines.values():
        e["score"] = round(100 * e.pop("points") / e["total"]) if e["total"] else 0

    # Share of voice from cited domains: unambiguous, and it names who wins instead of you.
    competitors = Counter()
    for r in responses:
        if r.error:
            continue
        for d in r.cited_domains:
            if d != domain and not d.endswith(f".{domain}"):
                competitors[d] += 1
    own = sum(1 for s in ok if s["cited"])
    total_citations = own + sum(competitors.values())

    return {
        "overall": overall,
        "brand": brand,
        "domain": domain,
        "prompts_run": len({s["prompt"] for s in scored}),
        "responses_ok": len(ok),
        "responses_failed": len(scored) - len(ok),
        "cited_count": own,
        "mentioned_count": sum(1 for s in ok if s["mentioned"]),
        "share_of_voice": round(100 * own / total_citations, 1) if total_citations else 0.0,
        "engines": sorted(engines.values(), key=lambda e: -e["score"]),
        "competitors": [
            {"domain": d, "citations": n, "share": round(100 * n / total_citations, 1)}
            for d, n in competitors.most_common(10)
        ],
        "responses": scored,
        "errors": sorted({s["error"] for s in scored if s["error"]}),
    }
