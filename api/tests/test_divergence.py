"""The divergence engine — the product's core claim.

Two things must hold. The verdict must work in both directions (a one-directional
"you're always worse at AI" is a sales pitch, not a measurement), and the
attribution of each failing check to an audience must follow the weights rather
than a hand-maintained list.
"""
import pytest

from audit import Ctx, analyse
from audit.checks import Finding
from audit.score import ALIGNED_BAND, _divergence, score
from tests.test_audit import HOSTILE_ROBOTS, PERMISSIVE_ROBOTS, make_snapshot


def f(fid, seo, geo, passed=False, severity="medium"):
    return Finding(fid, "cat", fid, passed, severity, "evidence",
                   fix="do the thing", seo_weight=seo, geo_weight=geo)


# ------------------------------------------------------------------- verdicts

def test_verdict_is_bidirectional():
    """If this only ever returns seo_ahead, the tool is measuring nothing."""
    seo_ahead = _divergence([], {"overall": 80}, {"overall": 40})
    geo_ahead = _divergence([], {"overall": 40}, {"overall": 80})
    aligned = _divergence([], {"overall": 70}, {"overall": 70})

    assert seo_ahead["verdict"] == "seo_ahead"
    assert geo_ahead["verdict"] == "geo_ahead"
    assert aligned["verdict"] == "aligned"
    assert seo_ahead["headline"] != geo_ahead["headline"] != aligned["headline"]


@pytest.mark.parametrize("gap,verdict", [
    (ALIGNED_BAND, "aligned"),
    (ALIGNED_BAND + 1, "seo_ahead"),
    (-ALIGNED_BAND, "aligned"),
    (-ALIGNED_BAND - 1, "geo_ahead"),
])
def test_aligned_band_boundaries(gap, verdict):
    d = _divergence([], {"overall": 50 + gap}, {"overall": 50})
    assert d["verdict"] == verdict


def test_gap_is_signed_and_abs_gap_is_not():
    d = _divergence([], {"overall": 30}, {"overall": 70})
    assert d["gap"] == -40 and d["abs_gap"] == 40


# ----------------------------------------------------------------- attribution

@pytest.mark.parametrize("seo,geo,audience", [
    (0.0, 3.0, "ai"),        # pure AI signal
    (3.0, 0.0, "search"),    # pure search signal
    (2.0, 2.0, "both"),      # equally weighted
    (3.0, 1.0, "search"),    # 3x skew
    (1.0, 3.0, "ai"),
    (0.0, 0.0, "neither"),   # training-only crawler tokens land here
])
def test_audience_follows_the_weights(seo, geo, audience):
    assert f("x", seo, geo).audience == audience


def test_failing_checks_are_bucketed_by_audience():
    findings = [
        f("ai_only", 0.0, 3.0),
        f("search_only", 3.0, 0.0),
        f("both", 2.0, 2.0),
        f("passed", 3.0, 3.0, passed=True),
    ]
    d = _divergence(findings, {"overall": 60}, {"overall": 40})
    assert [x["id"] for x in d["costs_ai"]] == ["ai_only"]
    assert [x["id"] for x in d["costs_search"]] == ["search_only"]
    assert [x["id"] for x in d["costs_both"]] == ["both"]


def test_passing_checks_never_appear_as_costs():
    d = _divergence([f("p", 3.0, 3.0, passed=True)], {"overall": 90}, {"overall": 90})
    assert not d["costs_ai"] and not d["costs_search"] and not d["costs_both"]


def test_contrasts_surface_the_widest_weight_gaps_first():
    report = score([
        Finding("no_js_content", "c", "JS", False, "critical", "e", fix="x"),
        Finding("named_author", "c", "Author", False, "medium", "e", fix="x"),
    ])
    contrasts = report["divergence"]["contrasts"]
    if len(contrasts) > 1:
        gaps = [abs(c["seo_weight"] - c["geo_weight"]) for c in contrasts]
        assert gaps == sorted(gaps, reverse=True)


# -------------------------------------------------------------- real fixtures

def test_client_rendered_page_skews_toward_search():
    """Googlebot executes JavaScript; answer engines do not."""
    r = analyse(Ctx(make_snapshot("bad.html")))
    assert r["divergence"]["verdict"] == "seo_ahead"
    assert r["seo"]["overall"] > r["geo"]["overall"]


def test_well_structured_docs_page_fails_mostly_on_the_search_side():
    """A page written for comprehension scores well for AI while leaving classic
    on-page hygiene undone. The failure composition is the signal."""
    # Declares its AI intent as well as permitting the fetch, which is what
    # separates a page built for answer engines from one merely open to them.
    robots = PERMISSIVE_ROBOTS + "Content-Signal: search=yes, ai-input=yes, ai-train=no\n"
    r = analyse(Ctx(make_snapshot("docs_geo_ahead.html", robots=robots, llms="# Meridian\n\nAPI docs for rate limits and quotas.\n")))
    d = r["divergence"]
    assert len(d["costs_search"]) > len(d["costs_ai"]), (
        f"expected search-side failures to dominate, got "
        f"{[x['id'] for x in d['costs_search']]} vs {[x['id'] for x in d['costs_ai']]}"
    )
    assert r["citability"]["score"] >= 60, "a dense, cited, answer-first page should score well"


def test_a_page_can_be_strong_for_ai_and_weak_for_search():
    """Guards against the scoring being structurally incapable of geo_ahead."""
    findings = [
        # search-side hygiene all failing
        Finding("title_length", "c", "Title", False, "high", "e", fix="x"),
        Finding("meta_desc_length", "c", "Desc", False, "medium", "e", fix="x"),
        Finding("viewport", "c", "Viewport", False, "high", "e", fix="x"),
        Finding("internal_links", "c", "Links", False, "medium", "e", fix="x"),
        Finding("render_blocking", "c", "Blocking", False, "medium", "e", fix="x"),
        Finding("dom_size", "c", "DOM", False, "low", "e", fix="x"),
        Finding("https", "c", "HTTPS", False, "critical", "e", fix="x"),
        # AI-side signals all passing
        Finding("answer_first", "c", "Answer first", True, "high", "e"),
        Finding("chunkability", "c", "Chunks", True, "medium", "e"),
        Finding("question_headings", "c", "Questions", True, "medium", "e"),
        Finding("named_author", "c", "Author", True, "medium", "e"),
        Finding("entity_schema", "c", "Entity", True, "high", "e"),
        Finding("multimodal", "c", "Media", True, "medium", "e"),
    ]
    r = score(findings, citability={"score": 85, "raw": 179, "max_possible": 210, "methods": []})
    assert r["geo"]["overall"] > r["seo"]["overall"]
    assert r["divergence"]["verdict"] == "geo_ahead"
    assert "search" in r["divergence"]["headline"].lower() or \
        "rankings" in r["divergence"]["headline"].lower()


# ------------------------------------------------------------------- caps

def test_blocking_only_citation_bots_caps_geo_and_not_seo():
    """Googlebot allowed, answer-engine crawlers blocked: search is unaffected."""
    robots = (
        "User-agent: *\nAllow: /\n"
        "User-agent: OAI-SearchBot\nDisallow: /\n"
        "User-agent: Claude-SearchBot\nDisallow: /\n"
        "User-agent: PerplexityBot\nDisallow: /\n"
        "User-agent: Applebot\nDisallow: /\n"
    )
    r = analyse(Ctx(make_snapshot("good.html", robots=robots)))
    googlebot = next(f for f in r["findings"] if f["id"] == "robots_googlebot")
    assert googlebot["passed"], "Googlebot should still be allowed"
    assert not r["seo"]["cap_reasons"], "search must not be capped when Googlebot is allowed"
    assert r["geo"]["overall"] < r["seo"]["overall"]
