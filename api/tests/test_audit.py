from dataclasses import replace
from pathlib import Path

import pytest

from audit import CHECKS, Ctx, Finding, score
from audit import bots
from audit.fetch import AI_BOTS, BotProbe, SiteSnapshot, _robots_allows
from audit.taxonomy import SEVERITY_RANK

FIXTURES = Path(__file__).parent / "fixtures"

PERMISSIVE_ROBOTS = "User-agent: *\nAllow: /\nSitemap: https://acme.example/sitemap.xml\n"
HOSTILE_ROBOTS = "User-agent: *\nDisallow: /\n"


def make_snapshot(fixture: str, *, robots=PERMISSIVE_ROBOTS, llms=None, sitemap=True, bot_status=200, **kw) -> SiteSnapshot:
    html = (FIXTURES / fixture).read_text()
    return SiteSnapshot(
        url="https://acme.example/guide/ai-search",
        final_url=kw.pop("final_url", "https://acme.example/guide/ai-search"),
        status=200,
        html=html,
        headers=kw.pop("headers", {}),
        ttfb_ms=kw.pop("ttfb_ms", 220.0),
        bytes=len(html),
        robots_txt=robots,
        llms_txt=llms,
        sitemap_urls=["https://acme.example/sitemap.xml"] if sitemap else [],
        robots_sitemap_refs=["https://acme.example/sitemap.xml"] if sitemap and "Sitemap:" in (robots or "") else [],
        bot_probes=[
            BotProbe(bot, bot_status, not _robots_allows(robots, bot, "/guide/ai-search")) for bot in AI_BOTS
        ],
    )


def run(snap: SiteSnapshot) -> dict:
    ctx = Ctx(snap)
    findings: list[Finding] = []
    for fn in CHECKS:
        r = fn(ctx)
        findings.extend(r if isinstance(r, list) else [r])
    return score(findings)


def by_id(result: dict) -> dict:
    return {f["id"]: f for f in result["findings"]}


# ------------------------------------------------------------------ robots parsing

@pytest.mark.parametrize(
    "robots,bot,path,expected",
    [
        (None, "GPTBot", "/", True),
        ("User-agent: *\nDisallow: /", "GPTBot", "/", False),
        ("User-agent: *\nDisallow:", "GPTBot", "/", True),
        ("User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /", "GPTBot", "/", False),
        ("User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /", "ClaudeBot", "/", True),
        # longest match wins over a broader disallow
        ("User-agent: *\nDisallow: /\nAllow: /blog/", "PerplexityBot", "/blog/post", True),
        ("User-agent: *\nDisallow: /\nAllow: /blog/", "PerplexityBot", "/other", False),
        # agent names are case-insensitive
        ("user-agent: gptbot\ndisallow: /", "GPTBot", "/", False),
        # wildcards and end-anchors
        ("User-agent: *\nDisallow: /*.pdf$", "GPTBot", "/files/a.pdf", False),
        ("User-agent: *\nDisallow: /*.pdf$", "GPTBot", "/files/a.pdf.html", True),
        # consecutive user-agent lines share one rule block
        ("User-agent: GPTBot\nUser-agent: ClaudeBot\nDisallow: /", "ClaudeBot", "/", False),
        # comments are stripped
        ("User-agent: *  # everyone\nDisallow: /  # nope", "GPTBot", "/", False),
    ],
)
def test_robots_evaluation(robots, bot, path, expected):
    assert _robots_allows(robots, bot, path) is expected


# ------------------------------------------------------------------- scoring bands

def test_good_page_scores_well_on_both_sides():
    result = run(make_snapshot("good.html", llms="# Acme Analytics\n\n> Analytics for AI search.\n\n## Key pages\n\n- [Guide](https://acme.example/guide): the guide\n"))
    failing = [f["title"] for f in result["findings"] if not f["passed"]]
    assert result["seo"]["overall"] >= 75, failing
    assert result["geo"]["overall"] >= 70, failing
    assert not result["seo"]["cap_reasons"] and not result["geo"]["cap_reasons"]


def test_bad_page_scores_badly_on_both_sides():
    result = run(make_snapshot("bad.html", robots=HOSTILE_ROBOTS, sitemap=False))
    assert result["seo"]["overall"] <= 40
    assert result["geo"]["overall"] <= 40
    assert result["seo"]["grade"] == "F" and result["geo"]["grade"] == "F"


def test_every_failed_finding_has_a_fix():
    """The fix is the product. A failing check with no remediation is a bug."""
    for fixture, robots in (("good.html", PERMISSIVE_ROBOTS), ("bad.html", HOSTILE_ROBOTS)):
        result = run(make_snapshot(fixture, robots=robots, sitemap=False))
        missing = [f["id"] for f in result["findings"] if not f["passed"] and not f["fix"]]
        assert not missing, f"{fixture}: findings with no fix: {missing}"


def test_passing_findings_carry_no_fix():
    result = run(make_snapshot("good.html"))
    assert not [f["id"] for f in result["findings"] if f["passed"] and f["fix"]]


# ----------------------------------------------------------------------- the caps

def test_blocked_crawlers_cap_both_scores():
    """Disallow: / blocks Googlebot AND every citation bot, so both sides cap."""
    result = run(make_snapshot("good.html", robots=HOSTILE_ROBOTS, sitemap=False))
    assert result["geo"]["overall"] <= 40
    assert result["seo"]["overall"] <= 40
    assert any("robots.txt" in r for r in result["geo"]["cap_reasons"])
    assert any("Googlebot" in r for r in result["seo"]["cap_reasons"])


def test_edge_block_is_detected_even_when_robots_is_permissive():
    result = run(make_snapshot("good.html", bot_status=403))
    findings = by_id(result)
    assert not findings["edge_block"]["passed"]
    assert findings["robots_gptbot"]["passed"], "robots.txt is permissive; only the edge is blocking"
    assert "403" in findings["edge_block"]["evidence"] or "rejected" in findings["edge_block"]["evidence"]


def test_client_rendering_hurts_ai_far_more_than_search():
    """The asymmetry that justifies the whole product: Googlebot executes JS,
    answer engines do not."""
    result = run(make_snapshot("bad.html"))
    finding = by_id(result)["no_js_content"]
    assert not finding["passed"] and "client-rendered" in finding["evidence"]

    assert finding["audience"] == "ai", "a CSR page is an AI problem, not a search problem"
    assert result["geo"]["overall"] < result["seo"]["overall"]
    assert result["divergence"]["verdict"] == "seo_ahead"
    assert not any("JavaScript" in r for r in result["seo"]["cap_reasons"]), \
        "search must never be capped for a JS-rendered page"
    assert finding["id"] in [f["id"] for f in result["divergence"]["costs_ai"]]


def test_unreadable_cap_binds_when_the_page_is_otherwise_strong():
    """The cap is a safety net: it only fires when it actually lowers the score."""
    from audit.checks import Finding
    from audit.score import UNREADABLE_CAP, score

    perfect = [
        Finding("no_js_content", "crawler", "Content readable without JavaScript",
                False, "critical", "client-rendered"),
        Finding("entity_schema", "structure", "Entity schema", True, "high", ""),
        Finding("named_author", "trust", "Named author", True, "medium", ""),
        Finding("statistics", "content", "Statistics", True, "medium", ""),
    ]
    result = score(perfect)
    assert result["geo"]["overall"] <= UNREADABLE_CAP
    assert any("JavaScript" in r for r in result["geo"]["cap_reasons"])
    assert not result["seo"]["cap_reasons"]


# -------------------------------------------------------------- individual checks

def test_good_page_detects_brand_and_entity_schema():
    ctx = Ctx(make_snapshot("good.html"))
    assert ctx.brand == "Acme Analytics"
    assert "Article" in ctx.schema_types()


def test_brand_falls_back_through_title_then_domain():
    snap = make_snapshot("bad.html")
    assert Ctx(snap).brand == "Acme"  # from <title>, no og:site_name

    snap.html = "<html><head></head><body><p>hi</p></body></html>"
    assert Ctx(snap).brand == "Acme"  # from the domain


def test_llms_txt_missing_is_reported_with_generated_file():
    result = run(make_snapshot("good.html", llms=None))
    finding = by_id(result)["llms_txt"]
    assert not finding["passed"]
    assert "# Acme Analytics" in finding["fix"]


def test_question_headings_and_answer_first_pass_on_good_page():
    findings = by_id(run(make_snapshot("good.html")))
    assert findings["question_headings"]["passed"]
    assert findings["answer_first"]["passed"]
    assert findings["chunkability"]["passed"]


def test_schema_required_fields_flags_incomplete_article():
    snap = make_snapshot("good.html")
    snap.html = snap.html.replace('"datePublished": "2026-01-15",', "")
    finding = by_id(run(snap))["schema_fields"]
    assert not finding["passed"]
    assert "datePublished" in finding["evidence"]


def test_broken_jsonld_is_reported_as_broken_not_missing():
    snap = make_snapshot("good.html")
    snap.html = snap.html.replace('"name": "Acme Analytics",', '"name": "Acme Analytics",,')
    finding = by_id(run(snap))["jsonld_present"]
    assert not finding["passed"]
    assert "does not parse" in finding["evidence"]


def test_slow_heavy_page_fails_delivery():
    finding = by_id(run(make_snapshot("good.html", ttfb_ms=4200.0)))["delivery_speed"]
    assert not finding["passed"]


def test_findings_are_ordered_failures_first_by_severity():
    result = run(make_snapshot("bad.html", robots=HOSTILE_ROBOTS, sitemap=False))
    failed = [f for f in result["findings"] if not f["passed"]]
    ranks = [SEVERITY_RANK[f["severity"]] for f in failed]
    assert ranks == sorted(ranks)
    assert result["findings"][0]["severity"] == "critical"


def test_category_weights_sum_to_one():
    from audit.taxonomy import GEO_WEIGHTS, SEO_WEIGHTS

    assert sum(SEO_WEIGHTS.values()) == pytest.approx(1.0)
    assert sum(GEO_WEIGHTS.values()) == pytest.approx(1.0)


def test_checks_are_order_independent():
    """Regression: body_text used to decompose <script> on the shared tree, wiping out
    the JSON-LD every later check reads. Shuffling the registry must not change results."""
    import random

    snap = make_snapshot("good.html")
    baseline = {f.id: f.passed for f in _findings(snap, CHECKS)}
    for seed in range(5):
        shuffled = CHECKS[:]
        random.Random(seed).shuffle(shuffled)
        assert {f.id: f.passed for f in _findings(snap, shuffled)} == baseline


def _findings(snap, checks) -> list[Finding]:
    ctx = Ctx(snap)
    out: list[Finding] = []
    for fn in checks:
        r = fn(ctx)
        out.extend(r if isinstance(r, list) else [r])
    return out


def test_body_text_does_not_mutate_the_shared_tree():
    ctx = Ctx(make_snapshot("good.html"))
    before = len(ctx.tree.css('script[type="application/ld+json"]'))
    _ = ctx.body_text
    assert len(ctx.tree.css('script[type="application/ld+json"]')) == before == 2


def test_generic_challenge_words_need_an_error_status():
    """A 200 page that merely mentions blocking is not an interstitial.

    Without the status gate, a security vendor's homepage or a post about bot
    filtering reads as edge-blocked and its AI score is suppressed.
    """
    prose = "<h1>We stop scrapers</h1><p>Requests are blocked and forbidden by captcha.</p>"
    assert bots.looks_challenged(prose, 200) is False
    assert bots.looks_challenged(prose, 403) is True

    # Vendor fingerprints stand on their own, which is the whole point of a
    # soft block: the status is 200 and only the body gives it away.
    assert bots.looks_challenged("<title>Just a moment...</title>", 200) is True
    assert bots.looks_challenged("<div id='cf-chl-widget'>", 200) is True


def test_information_density_separates_filler_from_fact():
    """The threshold is only meaningful if it discriminates.

    Calibration samples: generic marketing prose scores ~4 facts per 100 words,
    specific factual writing ~32. A bar that passes both is not a check.
    """
    import re as _re
    from audit.checks import _ENTITY_RE, _NUMBER_RE

    def density(t: str) -> float:
        return (len(_ENTITY_RE.findall(t)) + len(_NUMBER_RE.findall(t))) * 100.0 / len(t.split())

    generic = (
        "In today's fast paced world, businesses are looking for ways to improve their "
        "operations. It is important to note that many companies struggle with this. Our "
        "solution helps you unlock the potential of your team and elevate your workflow."
    )
    specific = (
        "Stripe processed 1.4 trillion dollars in 2024, up 38 percent from 2023. Checkout "
        "supports 47 currencies across 135 countries. Klarna cut latency from 340ms to 95ms."
    )
    assert density(generic) < 8.0 <= density(specific)


def test_payment_required_counts_as_blocked():
    """402 is a hard block on citability, not a transient error.

    Cloudflare pay-per-crawl and x402 both answer AI crawlers with 402 while
    Googlebot is served normally. Scoring that as reachable would hide the
    single most direct cause of an AI-visibility gap.
    """
    assert 402 in bots.BLOCKED_STATUSES
    probe = BotProbe("OAI-SearchBot", 402, False, body_len=463)
    assert probe.blocked_by_edge is True
    assert probe.reachable is False


def test_input_wrapped_in_label_counts_as_labelled():
    """`<label><span>Email</span><input></label>` needs no `for`.

    Implicit association is valid HTML and gives the input an accessible name.
    Flagging it reports a correctly built form as broken.
    """
    html = (
        "<html><body><form>"
        '<label><span>Email</span><input name="email" type="email"></label>'
        '<label for="co">Company</label><input id="co" name="company">'
        '<input name="orphan" type="text">'
        "</form></body></html>"
    )
    snap = make_snapshot("good.html")
    f = next(fn for fn in CHECKS if fn.__name__ == "labelled_inputs")(Ctx(replace(snap, html=html)))
    assert not f.passed, "the orphan input should still fail"
    assert "1 of 3" in f.evidence, f.evidence


def test_picture_sources_count_as_modern_formats():
    """<picture> with AVIF/WebP <source>s serves a modern format even though its
    <img src> fallback is a JPEG. Reading only the <img> called that legacy."""
    html = ("<html><body>"
            + '<picture><source type="image/avif" srcset="a.avif"><source type="image/webp" srcset="a.webp">'
              '<img src="a.jpg" alt="x"></picture>' * 4
            + "</body></html>")
    f = next(fn for fn in CHECKS if fn.__name__ == "image_formats")(Ctx(replace(make_snapshot("good.html"), html=html)))
    assert f.passed, f.evidence
    assert "0/4 images use JPEG/PNG; 4 use srcset" in f.evidence, f.evidence


@pytest.mark.parametrize("path", ["/", "/de", "/fr", "/fr-ca/"])
def test_breadcrumbs_do_not_apply_to_home_pages(path):
    """A home page, including a language root, is the root of every trail."""
    snap = replace(make_snapshot("good.html"), final_url=f"https://acme.example{path}")
    f = next(fn for fn in CHECKS if fn.__name__ == "breadcrumbs")(Ctx(snap))
    assert f.passed and "Home page" in f.evidence


def test_breadcrumbs_still_required_below_the_home_page():
    snap = replace(make_snapshot("good.html"), final_url="https://acme.example/guide/ai-search")
    f = next(fn for fn in CHECKS if fn.__name__ == "breadcrumbs")(Ctx(snap))
    assert "Home page" not in f.evidence


def _check(name: str, html: str) -> Finding:
    return next(fn for fn in CHECKS if fn.__name__ == name)(Ctx(replace(make_snapshot("good.html"), html=html)))


def test_async_nomodule_and_module_scripts_do_not_block_render():
    """Boolean attributes parse to None, so a truthiness test called every
    `<script async>` render-blocking. Next.js ships exactly this head."""
    head = ('<script src="a.js" async></script><script src="b.js" async=""></script>'
            '<script src="c.js" defer></script><script src="d.js" noModule></script>'
            '<script src="e.js" type="module"></script>')
    assert _check("render_blocking", f"<html><head>{head}</head><body></body></html>").passed
    f = _check("render_blocking", f'<html><head>{head}<script src="f.js"></script></head><body></body></html>')
    assert not f.passed and f.evidence.startswith("1 script"), f.evidence


def test_decorative_alt_is_not_missing_alt():
    """alt="" declares an image decorative, as the check's own fix text says."""
    assert _check("image_alt_text", '<html><body><img src="a.svg" alt=""><img src="b.svg" alt></body></html>').passed
    f = _check("image_alt_text", '<html><body><img src="a.svg" alt=""><img src="b.png"></body></html>')
    assert not f.passed and "1 with no alt" in f.evidence, f.evidence
