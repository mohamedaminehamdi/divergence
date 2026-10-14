"""Dual scoring: one score for search crawlers, one for answer engines, and the
gap between them.

The caps are deliberately asymmetric, because the failure modes are. A page that
needs JavaScript to render can rank perfectly well on Google — Googlebot executes
JS — while being a blank page to every answer engine. Capping both scores for
that would erase the exact finding the product exists to surface.
"""
from __future__ import annotations

from . import bots
from .checks import Finding, apply_weights
from .promise import build_promise
from .taxonomy import (
    GEO_LABELS, GEO_WEIGHTS, SEO_LABELS, SEO_WEIGHTS, SEVERITY_RANK, band, grade,
)

BLOCKED_CAP = 40
UNREADABLE_CAP = 50
ALIGNED_BAND = 10  # |gap| at or under this is "aligned"


def _side(findings: list[Finding], kind: str, citability: int | None = None) -> dict:
    """Weighted score for one audience. Zero-weight checks are excluded entirely —
    a check that genuinely does not matter to this audience must not dilute it."""
    weights = SEO_WEIGHTS if kind == "seo" else GEO_WEIGHTS
    labels = SEO_LABELS if kind == "seo" else GEO_LABELS
    key = "seo_category" if kind == "seo" else "geo_dimension"
    wattr = "seo_weight" if kind == "seo" else "geo_weight"

    categories = []
    for cat, cat_weight in weights.items():
        items = [f for f in findings if getattr(f, key) == cat and getattr(f, wattr) > 0]
        if not items:
            continue
        earned = sum(getattr(f, wattr) for f in items if f.passed)
        total = sum(getattr(f, wattr) for f in items)
        categories.append({
            "key": cat,
            "label": labels[cat],
            "score": round(100 * earned / total) if total else 0,
            "weight": cat_weight,
            "passed": sum(1 for f in items if f.passed),
            "total": len(items),
        })

    if kind == "geo" and citability is not None:
        from .taxonomy import CITABILITY
        categories = [c for c in categories if c["key"] != CITABILITY]
        categories.append({
            "key": CITABILITY, "label": GEO_LABELS[CITABILITY], "score": citability,
            "weight": GEO_WEIGHTS[CITABILITY], "passed": 0, "total": 47,
            "continuous": True,
        })
        categories.sort(key=lambda c: -c["weight"])

    denom = sum(c["weight"] for c in categories) or 1
    overall = round(sum(c["score"] * c["weight"] for c in categories) / denom)
    return {"overall": overall, "categories": categories}


def _apply_caps(findings: list[Finding], seo: dict, geo: dict) -> tuple[list[str], list[str]]:
    """Returns (seo_caps, geo_caps) as human reasons, mutating the scores."""
    seo_reasons: list[str] = []
    geo_reasons: list[str] = []

    def cap(side: dict, reasons: list[str], value: int, why: str) -> None:
        if side["overall"] > value:
            side["overall"] = value
            reasons.append(why)

    by_id = {f.id: f for f in findings}

    # Citation crawlers decide whether an answer engine can quote you at all.
    citation = [f for f in findings
                if f.id.startswith("robots_") and _bot_of(f.id) in bots.CITATION_BOTS]
    if citation and not any(f.passed for f in citation):
        cap(geo, geo_reasons, BLOCKED_CAP,
            "Every citation crawler is disallowed in robots.txt. No answer engine can quote this page.")

    google = by_id.get("robots_googlebot")
    if google and not google.passed:
        cap(seo, seo_reasons, BLOCKED_CAP,
            "Googlebot is disallowed in robots.txt. Nothing else can matter for search.")

    edge = by_id.get("edge_block")
    if edge and not edge.passed:
        cap(geo, geo_reasons, BLOCKED_CAP, "AI crawlers are blocked at the CDN or WAF.")

    # The asymmetric one. Googlebot renders JavaScript; no answer engine does.
    readable = by_id.get("no_js_content")
    if readable and not readable.passed:
        cap(geo, geo_reasons, UNREADABLE_CAP,
            "The page has no content without JavaScript, which answer engines do not execute. "
            "Search is unaffected, because Googlebot renders JS.")

    return seo_reasons, geo_reasons


def _bot_of(check_id: str) -> str | None:
    slug = check_id.removeprefix("robots_")
    for bot in bots.BOTS:
        if bot.lower().replace("-", "_") == slug:
            return bot
    return None


def _divergence(findings: list[Finding], seo: dict, geo: dict) -> dict:
    gap = seo["overall"] - geo["overall"]

    if abs(gap) <= ALIGNED_BAND:
        verdict, headline = "aligned", "Both audiences see you about the same."
    elif gap > 0:
        verdict = "seo_ahead"
        headline = "Google can find you. AI can't cite you."
    else:
        verdict = "geo_ahead"
        headline = "AI-ready, but you're leaving search rankings on the table."

    failed = [f for f in findings if not f.passed]
    costs_ai = sorted([f for f in failed if f.audience == "ai"], key=lambda f: -f.geo_weight)
    costs_search = sorted([f for f in failed if f.audience == "search"], key=lambda f: -f.seo_weight)
    costs_both = sorted([f for f in failed if f.audience == "both"],
                        key=lambda f: -(f.seo_weight + f.geo_weight))

    return {
        "gap": gap,
        "abs_gap": abs(gap),
        "verdict": verdict,
        "headline": headline,
        "summary": _summary(verdict, gap, costs_ai, costs_search, costs_both),
        "costs_ai": [_brief(f) for f in costs_ai],
        "costs_search": [_brief(f) for f in costs_search],
        "costs_both": [_brief(f) for f in costs_both],
        "contrasts": _contrasts(findings),
    }


def _contrasts(findings: list[Finding]) -> list[dict]:
    """The widest weight gaps, one row per idea.

    The per-bot robots checks all carry identical weights, so listing five of them
    crowds out five genuinely different insights. They collapse into one row.
    """
    seen_citation_bot = False
    out: list[dict] = []
    for f in sorted(findings, key=lambda f: -abs(f.divergence)):
        if not f.note or abs(f.divergence) < 1.0:
            continue
        if f.id.startswith("robots_"):
            bot = _bot_of(f.id)
            if bot in bots.CITATION_BOTS and bot != "Googlebot":
                if seen_citation_bot:
                    continue
                seen_citation_bot = True
                group = [g for g in findings
                         if g.id.startswith("robots_")
                         and (_bot_of(g.id) in bots.CITATION_BOTS)
                         and _bot_of(g.id) != "Googlebot"]
                blocked = [_bot_of(g.id) for g in group if not g.passed]
                out.append({
                    "id": "robots_citation_bots",
                    "title": f"robots.txt allows the {len(group)} citation crawlers",
                    "note": "These tokens decide whether an answer engine may quote you. They are "
                            "separate from the training tokens, which cost you nothing either way.",
                    "seo_weight": f.seo_weight,
                    "geo_weight": f.geo_weight,
                    "passed": not blocked,
                })
                continue
        out.append({"id": f.id, "title": f.title, "note": f.note,
                    "seo_weight": f.seo_weight, "geo_weight": f.geo_weight, "passed": f.passed})
        if len(out) >= 8:
            break
    return out[:8]


def _summary(verdict: str, gap: int, ai: list, search: list, both: list) -> str:
    if verdict == "seo_ahead":
        return (
            f"Your search score leads your AI score by {abs(gap)} points. "
            f"{len(ai)} check{'s' if len(ai) != 1 else ''} fail only for answer engines, "
            "work that classic SEO would never flag, and that is where the gap lives."
        )
    if verdict == "geo_ahead":
        return (
            f"Your AI score leads your search score by {abs(gap)} points. "
            f"You are well structured for citation but {len(search)} check"
            f"{'s' if len(search) != 1 else ''} fail on the search side."
        )
    return (
        f"The two scores are within {abs(gap)} points. "
        f"{len(both)} issue{'s' if len(both) != 1 else ''} cost you with both audiences at once. "
        "fix those first, they pay twice."
    )


def _brief(f: Finding) -> dict:
    return {"id": f.id, "title": f.title, "severity": f.severity, "evidence": f.evidence,
            "seo_weight": f.seo_weight, "geo_weight": f.geo_weight, "note": f.note}


def score(findings: list[Finding], citability: dict | None = None) -> dict:
    # Applied here rather than only in run_all: main.py and audit.audit() build
    # their own finding lists, and an unweighted list scores a silent zero.
    # This is idempotent, so the choke point is safe to call from anywhere.
    apply_weights(findings)

    cit_score = citability["score"] if citability else None
    seo, geo = _side(findings, "seo"), _side(findings, "geo", cit_score)
    seo_caps, geo_caps = _apply_caps(findings, seo, geo)

    for side, caps, kind in ((seo, seo_caps, "seo"), (geo, geo_caps, "geo")):
        side["grade"] = grade(side["overall"])
        side["band"] = band(side["overall"])
        side["cap_reasons"] = caps
        side["kind"] = kind

    ordered = sorted(
        findings,
        key=lambda f: (f.passed, SEVERITY_RANK[f.severity], -(f.seo_weight + f.geo_weight)),
    )

    return {
        "seo": seo,
        "geo": geo,
        "divergence": _divergence(findings, seo, geo),
        "promise": build_promise(findings, seo["overall"], geo["overall"], cit_score),
        "citability": citability,
        "passed_count": sum(1 for f in findings if f.passed),
        "total_count": len(findings),
        "findings": [_as_dict(f) for f in ordered],
        "disclaimer": (
            "Scores are heuristics computed from this page. They are not Google or any AI "
            "provider's own metrics, and no third-party tool has access to their ranking data."
        ),
    }


def _as_dict(f: Finding) -> dict:
    return {
        "id": f.id, "title": f.title, "passed": f.passed, "severity": f.severity,
        "evidence": f.evidence, "fix": f.fix, "note": f.note,
        "audience": f.audience, "effort": f.effort, "advisory": f.advisory,
        "seo_category": f.seo_category, "seo_weight": f.seo_weight,
        "geo_dimension": f.geo_dimension, "geo_weight": f.geo_weight,
    }
