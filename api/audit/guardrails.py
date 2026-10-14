"""Executable anti-hallucination rules.

Both source repos hard-code constraints that automated auditors routinely get
wrong — recommending schema Google retired, citing the wrong crawler token as
evidence, or inventing metrics that do not exist. Those constraints live here as
assertions over a finished report rather than as prose in a doc, because a rule
nobody runs is a rule that rots.

`verify()` returns a list of violations. The test suite asserts it is empty for
every fixture and every live page we audit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import bots

# Metrics that do not exist, or no longer exist. Naming any of them in output is
# an instant credibility loss with anyone who knows the field.
BANNED_TERMS = {
    r"\bFID\b": "FID was replaced by INP on 2024-03-12 and removed from CrUX/PSI. Never reference it.",
    r"first input delay": "First Input Delay is retired. Use INP.",
    r"core web vitals 2\.0": "There is no Core Web Vitals 2.0.",
    r"\bCWV 2\.0\b": "There is no Core Web Vitals 2.0.",
    r"visual stability index": "There is no Visual Stability Index metric.",
    r"engagement reliability": "There is no Engagement Reliability metric.",
}

# Schema types Google has deprecated. Recommending them sends users to build
# markup that produces nothing.
DEPRECATED_SCHEMA = (
    "HowTo", "SpecialAnnouncement", "CourseInfo", "EstimatedSalary",
    "LearningVideo", "ClaimReview", "VehicleListing",
)

# Retired rich result, but the markup is harmless and the structure still helps
# comprehension. It must never be reported above Info, and removal must never be
# recommended.
SOFT_SCHEMA = ("FAQPage",)

# Training-only crawler tokens. Blocking them says nothing about citability.
TRAINING_ONLY = bots.TRAINING

RECOMMEND_VERBS = r"(?:add|use|implement|recommend|create|mark ?up|switch to)"

# Verbatim content quoted from the page being audited. Exempt from our own
# typography rules, because it is evidence rather than prose we wrote.
QUOTED_RE = re.compile(r'"[^"]*"')


@dataclass
class Violation:
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.detail}"


def _text_of(report: dict) -> list[tuple[str, str]]:
    """(where, text) for every user-visible string in the report."""
    out: list[tuple[str, str]] = []
    for f in report.get("findings", []):
        for key in ("title", "evidence", "fix", "note"):
            if f.get(key):
                out.append((f"finding:{f['id']}:{key}", f[key]))
    for side in ("seo", "geo"):
        for reason in report.get(side, {}).get("cap_reasons", []):
            out.append((f"{side}:cap", reason))
    d = report.get("divergence", {})
    for key in ("headline", "summary"):
        if d.get(key):
            out.append((f"divergence:{key}", d[key]))
    for c in d.get("contrasts", []):
        if c.get("note"):
            out.append((f"contrast:{c['id']}", c["note"]))
    if report.get("promise", {}).get("headline"):
        out.append(("promise:headline", report["promise"]["headline"]))
    if report.get("disclaimer"):
        out.append(("disclaimer", report["disclaimer"]))
    return out


def verify(report: dict) -> list[Violation]:
    v: list[Violation] = []
    texts = _text_of(report)
    findings = {f["id"]: f for f in report.get("findings", [])}

    # 0. Typography: no em-dash or en-dash in anything a user reads. It is the
    #    single clearest "written by an LLM" tell, and this report is a sales asset.
    #    Double-quoted spans are exempt: those are the audited page's own content
    #    quoted verbatim, and rewriting someone's title would misreport it.
    for where, text in texts:
        ours = QUOTED_RE.sub('""', text)
        for ch, name in (("\u2014", "em-dash"), ("\u2013", "en-dash")):
            if ch in ours:
                v.append(Violation(
                    "dash-typography",
                    f"{where} contains an {name}. Restructure with a period, comma or colon; "
                    "use a plain hyphen for ranges.",
                ))

    # 1-3. Retired or invented metrics must never appear anywhere.
    for where, text in texts:
        for pattern, why in BANNED_TERMS.items():
            if re.search(pattern, text, re.I):
                v.append(Violation("banned-term", f"{where} mentions a retired/nonexistent metric. {why}"))

    # 4. Never recommend deprecated schema types.
    for where, text in texts:
        for t in DEPRECATED_SCHEMA:
            if re.search(rf"{RECOMMEND_VERBS}[^.]{{0,40}}\b{t}\b", text, re.I):
                v.append(Violation("deprecated-schema", f"{where} recommends {t}, which Google deprecated."))

    # 5. FAQPage: never above Info severity *when it is the subject*, never
    #    recommend adding or removing it, never claim a citation benefit.
    #    Merely naming it to explain that it is retired is allowed and correct.
    for f in report.get("findings", []):
        blob = " ".join(str(f.get(k) or "") for k in ("title", "evidence", "fix"))
        if not any(t in blob for t in SOFT_SCHEMA):
            continue
        subject = "FAQPage" in (f.get("title") or "") or re.search(
            r"FAQPage(?: schema)?(?: is)?\s*(?:missing|absent|not (?:present|found))", blob, re.I)
        if subject and f.get("severity") in ("critical", "high"):
            v.append(Violation("faqpage-severity",
                               f"finding:{f['id']} raises FAQPage to {f['severity']}; Info only."))
        if re.search(r"(?:remove|delete|strip|drop)[^.]{0,30}FAQPage", blob, re.I):
            v.append(Violation("faqpage-removal", f"finding:{f['id']} recommends removing FAQPage."))
        if re.search(rf"{RECOMMEND_VERBS}[^.]{{0,40}}FAQPage", blob, re.I):
            v.append(Violation("faqpage-recommended",
                               f"finding:{f['id']} recommends FAQPage markup. Google retired FAQ "
                               "rich results for all sites; use QAPage for genuine user Q&A."))

    # 6. Training-only crawler tokens must not carry scoring weight on either side,
    #    and must never be described as a citability lever.
    for fid, f in findings.items():
        if not fid.startswith("robots_"):
            continue
        bot = _bot_of(fid)
        if bot and bot in TRAINING_ONLY:
            if f.get("seo_weight", 0) or f.get("geo_weight", 0):
                v.append(Violation(
                    "training-bot-weighted",
                    f"{bot} is a training-only token but carries weight "
                    f"(seo={f.get('seo_weight')}, geo={f.get('geo_weight')}). "
                    "Blocking it does not affect citability.",
                ))
            blob = " ".join(str(f.get(k) or "") for k in ("evidence", "fix", "note"))
            if re.search(r"\bcit(?:e|es|ed|ing|ation|ations|able|abilit)|cannot be quoted",
                         blob, re.I) and \
               not re.search(r"does NOT affect|not affect|licensing choice", blob, re.I):
                v.append(Violation(
                    "training-bot-citability-claim",
                    f"{bot} is described as affecting citations without the correction.",
                ))

    # 7. llms.txt carries zero search weight — Google states it ignores the file.
    llms = findings.get("llms_txt")
    if llms and llms.get("seo_weight", 0) != 0:
        v.append(Violation("llms-txt-seo-weight",
                           "llms.txt must carry zero SEO weight; Google ignores the file entirely."))

    # 8. Never flag lazy-loading when a JS lazy-loader is in use.
    lazy = findings.get("lazy_loading")
    if lazy and not lazy["passed"] and re.search(r"lazy-?loader", lazy.get("evidence", ""), re.I):
        v.append(Violation("lazy-loader-false-positive",
                           "Flagged lazy loading despite detecting a JS lazy-loader."))

    # 9. Never flag missing <priority>/<changefreq> — Google ignores both.
    for where, text in texts:
        if re.search(rf"{RECOMMEND_VERBS}[^.]{{0,30}}<?(?:priority|changefreq)>?", text, re.I):
            v.append(Violation("sitemap-ignored-tags",
                               f"{where} recommends priority/changefreq, which Google ignores."))

    # 10. Advisories must never carry scoring weight — the evidence is already
    #     counted in a continuously-scored dimension.
    for f in report.get("findings", []):
        if f.get("advisory") and (f.get("seo_weight", 0) or f.get("geo_weight", 0)):
            v.append(Violation(
                "advisory-weighted",
                f"finding:{f['id']} is advisory but carries weight "
                f"(seo={f.get('seo_weight')}, geo={f.get('geo_weight')}). "
                "The same evidence would be counted twice.",
            ))

    # 11. The report must always state that these are heuristics.
    disclaimer = report.get("disclaimer", "")
    if not disclaimer or "heuristic" not in disclaimer.lower():
        v.append(Violation("missing-disclaimer",
                           "Report must state that scores are heuristics with no access to "
                           "Google's or any AI provider's ranking data."))

    # 11. The promise must never exceed what the simulation can justify.
    p = report.get("promise") or {}
    if p:
        for side in ("seo", "geo"):
            now, ceiling = p.get(f"{side}_now"), p.get(f"{side}_ceiling")
            if now is not None and ceiling is not None and ceiling < now:
                v.append(Violation("promise-regression",
                                   f"{side} ceiling {ceiling} is below the current score {now}."))
            if ceiling is not None and ceiling > 100:
                v.append(Violation("promise-impossible", f"{side} ceiling {ceiling} exceeds 100."))

    # 12. Backlink scoring gate: under 4 of 7 factors, no number may be emitted.
    bl = report.get("backlinks")
    if bl is not None:
        scored = bl.get("factors_scored", 0)
        if scored < 4 and bl.get("score") is not None:
            v.append(Violation("backlink-gate",
                               f"Emitted a backlink score with only {scored}/7 factors. "
                               "Must report the literal 'Not Assessed'."))

    return v


def _bot_of(check_id: str) -> str | None:
    slug = check_id.removeprefix("robots_")
    for bot in bots.BOTS:
        if bot.lower().replace("-", "_") == slug:
            return bot
    return None


def assert_clean(report: dict) -> None:
    """Raise if any guardrail is violated. Used in tests and CI."""
    violations = verify(report)
    if violations:
        raise AssertionError("guardrail violations:\n  " + "\n  ".join(str(x) for x in violations))
