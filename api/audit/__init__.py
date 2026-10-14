from . import citability as citability_engine
from .checks import CHECKS, Ctx, Finding, apply_weights, run_all
from . import seo_checks as _seo_checks  # registers the classic-SEO checks
from .citability_advice import advisories
from .fetch import snapshot
from .score import score


def analyse(ctx: Ctx, emit=None) -> dict:
    """Run every check plus the citability engine against an already-fetched page.

    Single entry point on purpose: main.py and audit() both used to inline this
    loop, which is how the weighting step went missing from one of them.

    `emit` reports each check as it completes. Every event names a check that
    genuinely ran against this page; the stream invents nothing to pad the
    animation.
    """
    findings: list[Finding] = []
    for fn in CHECKS:
        result = fn(ctx)
        batch = result if isinstance(result, list) else [result]
        findings.extend(batch)
        if emit and batch:
            emit({"type": "check", "title": batch[0].title,
                  "passed": all(f.passed for f in batch)})

    cit = citability_engine.run(ctx)
    findings.extend(advisories(cit))
    if emit:
        emit({"type": "check", "title": "Citability engine",
              "passed": cit.get("score", 0) >= 60})

    scored = score(findings, citability=cit)
    scored["url"] = ctx.snap.final_url
    scored["brand"] = ctx.brand
    return scored


async def audit(url: str) -> tuple[dict, str]:
    """Fetch a URL and return (scored audit, detected brand name)."""
    ctx = Ctx(await snapshot(url))
    scored = analyse(ctx)
    return scored, ctx.brand


__all__ = ["analyse", "audit", "snapshot", "run_all", "score", "Ctx", "Finding",
           "CHECKS", "apply_weights", "citability_engine", "advisories"]
