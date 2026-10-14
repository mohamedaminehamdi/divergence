"""What the score becomes once the fixable things are fixed.

This is the commercial claim, so it is computed rather than asserted. For each
effort bucket we take the findings that are actually failing, mark them passed,
and re-run the real scorer. The projected number is therefore exactly what the
audit would report after that work — not an estimate, and never a round number
chosen because it sells well.

Two honesty rules are enforced here:
  * A finding with no fix attached is not counted as recoverable.
  * The ceiling is whatever the simulation returns. If that is 71, the page says
    71. There is no floor, no rounding up, and no minimum uplift.
"""
from __future__ import annotations

from copy import deepcopy

from .checks import Finding
from .taxonomy import BUCKET_LABELS, EFFORT_BUCKETS, EFFORT_DESCRIPTIONS

BUCKET_ORDER = ["quick", "standard", "heavy"]


def _rescore(findings: list[Finding], citability: int | None) -> tuple[int, int]:
    from .score import _apply_caps, _side

    seo, geo = _side(findings, "seo"), _side(findings, "geo", citability)
    _apply_caps(findings, seo, geo)
    return seo["overall"], geo["overall"]


def _recoverable(f: Finding) -> bool:
    """Only count what we could actually hand someone instructions for."""
    return not f.passed and f.fix is not None and (f.seo_weight > 0 or f.geo_weight > 0)


def build_promise(findings: list[Finding], seo_now: int, geo_now: int,
                  citability: int | None = None) -> dict:
    fixable = [f for f in findings if _recoverable(f)]

    by_bucket: dict[str, list[Finding]] = {b: [] for b in BUCKET_ORDER}
    for f in fixable:
        bucket, _, _ = EFFORT_BUCKETS.get(f.effort, EFFORT_BUCKETS["hours"])
        by_bucket[bucket].append(f)

    steps, fixed_ids, seo_prev, geo_prev = [], set(), seo_now, geo_now
    for bucket in BUCKET_ORDER:
        items = by_bucket[bucket]
        if not items:
            continue
        fixed_ids |= {f.id for f in items}

        simulated = deepcopy(findings)
        for f in simulated:
            if f.id in fixed_ids:
                f.passed = True
        seo_after, geo_after = _rescore(simulated, citability)

        _, timeframe, days = EFFORT_BUCKETS[items[0].effort]
        steps.append({
            "bucket": bucket,
            "label": BUCKET_LABELS[bucket],
            "timeframe": timeframe,
            "days": days,
            "fix_count": len(items),
            "effort": EFFORT_DESCRIPTIONS.get(items[0].effort, ""),
            "seo_after": seo_after,
            "geo_after": geo_after,
            "seo_gain": seo_after - seo_prev,
            "geo_gain": geo_after - geo_prev,
            "fixes": [{"id": f.id, "title": f.title, "audience": f.audience} for f in items],
        })
        seo_prev, geo_prev = seo_after, geo_after

    # The ceiling: everything fixable, fixed.
    everything = deepcopy(findings)
    for f in everything:
        if f.id in {x.id for x in fixable}:
            f.passed = True
    seo_ceiling, geo_ceiling = _rescore(everything, citability)

    blocked = [
        {"id": f.id, "title": f.title, "evidence": f.evidence}
        for f in findings
        if not f.passed and f.fix is None and (f.seo_weight > 0 or f.geo_weight > 0)
    ]

    days = max((s["days"] for s in steps), default=0)
    measured = sum(1 for f in findings if f.seo_weight > 0 or f.geo_weight > 0)
    return {
        "checks_measured": measured,
        "seo_now": seo_now,
        "geo_now": geo_now,
        "seo_ceiling": seo_ceiling,
        "geo_ceiling": geo_ceiling,
        "seo_gain": seo_ceiling - seo_now,
        "geo_gain": geo_ceiling - geo_now,
        "days": days,
        "fix_count": len(fixable),
        "steps": steps,
        "blocked": blocked,
        "headline": _headline(seo_now, geo_now, seo_ceiling, geo_ceiling, days, measured),
        "achievable": bool(steps) and (seo_ceiling > seo_now or geo_ceiling > geo_now),
    }


def _headline(seo_now: int, geo_now: int, seo_max: int, geo_max: int, days: int, measured: int) -> str:
    seo_gain, geo_gain = seo_max - seo_now, geo_max - geo_now
    if seo_gain <= 0 and geo_gain <= 0:
        return "This page is already at the ceiling of what this audit can measure."

    # Lead with whichever side has the most to gain — that is the honest pitch.
    if geo_gain >= seo_gain:
        lead = f"AI visibility {geo_now} → {geo_max}"
        other = f"search {seo_now} → {seo_max}" if seo_gain > 0 else None
    else:
        lead = f"Search {seo_now} → {seo_max}"
        other = f"AI visibility {geo_now} → {geo_max}" if geo_gain > 0 else None

    window = f"in {days} days" if days else "immediately"
    # Name the basis. A bare "-> 100" reads as marketing; "100 across the N checks
    # this audit measures" is the same number and an actually defensible claim.
    return f"{lead}{f', {other}' if other else ''}, {window}, across the {measured} checks this audit measures."
