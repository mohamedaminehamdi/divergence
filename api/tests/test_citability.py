"""Port fidelity for the 47-method citability engine.

The value of this engine is that its thresholds come from measured citation
studies rather than intuition, so an off-by-one in a boundary silently destroys
the thing that makes it worth having. These tests pin the boundaries.
"""
import pytest
from selectolax.parser import HTMLParser

from audit import citability as cit
from audit.citability import METHODS, CitCtx


def ctx(body: str, *, jsonld=None, domain="acme.example") -> CitCtx:
    html = f"<html><body>{body}</body></html>"
    tree = HTMLParser(html)
    text_tree = HTMLParser(html)
    for tag in ("script", "style"):
        for n in text_tree.css(tag):
            n.decompose()
    import re
    text = re.sub(r"\s+", " ", (text_tree.body or text_tree).text(separator=" ")).strip()
    headings = [(int(n.tag[1]), n.text().strip()) for n in tree.css("h1,h2,h3,h4,h5,h6")]
    links = [(a.attributes.get("href", ""), a.text().strip()) for a in tree.css("a[href]")]
    return CitCtx(text=text, tree=tree, headings=headings, jsonld=jsonld or [],
                  links=links, domain=domain, headers={})


def run_method(name: str, c: CitCtx):
    fn = next(f for n, _, f in METHODS if n == name)
    return fn(c)


def words(n: int, token: str = "word") -> str:
    return " ".join([token] * n)


def distinct_words(n: int) -> str:
    """n distinct 4+ letter alphabetic words.

    The stuffing tokenizer is [a-zA-Z]{4,}, so "w0"-style tokens are discarded
    and "word0"-style tokens all collapse to the same token "word".
    """
    import string
    letters = string.ascii_lowercase
    out = []
    for i in range(n):
        a, b, c_ = i // 676, (i // 26) % 26, i % 26
        out.append(f"qq{letters[a]}{letters[b]}{letters[c_]}")
    return " ".join(out)


# ------------------------------------------------------------------- structure

def test_denominator_matches_the_source():
    assert len(METHODS) == 47
    assert cit.MAX_POSSIBLE == 210


def test_no_method_can_exceed_its_maximum():
    """run() clamps, so a buggy method degrades instead of inflating the score."""
    c = ctx("<p>" + words(500) + "</p>")
    result = cit.run(_FakeCtx(c))
    for m in result["methods"]:
        assert 0 <= m["score"] <= m["max_score"], m


class _FakeCtx:
    """Adapts a CitCtx to the audit Ctx surface that cit.run() reads."""
    def __init__(self, c: CitCtx):
        self.body_text, self.tree, self.headings = c.text, c.tree, c.headings
        self.jsonld, self.links = c.jsonld, c.links
        self.snap = type("S", (), {"domain": c.domain, "headers": {}})()


def test_score_is_raw_over_210():
    result = cit.run(_FakeCtx(ctx("<p>" + words(300) + "</p>")))
    assert result["max_possible"] == 210
    assert result["score"] == round(100 * result["raw"] / 210)


# ------------------------------------------------------- passage_density 50-150

@pytest.mark.parametrize("n,expect_dense", [(49, False), (50, True), (150, True), (151, False)])
def test_passage_density_band_is_inclusive_50_to_150(n, expect_dense):
    """Source band is 50-150 words inclusive, and the paragraph must contain a number."""
    c = ctx(f"<p>In 2026 {words(n - 2)}</p>")
    score, detected, detail = run_method("passage_density", c)
    assert (score > 0) is expect_dense, detail


def test_passage_density_requires_a_number():
    c = ctx(f"<p>{words(80)}</p>")
    score, _, _ = run_method("passage_density", c)
    assert score == 0, "a paragraph with no number is not a dense passage"


# --------------------------------------------------- answer_capsule 30-120 words

@pytest.mark.parametrize("n,ok", [(29, False), (30, True), (120, True), (121, False)])
def test_answer_capsule_word_band(n, ok):
    c = ctx(f"<p>Revenue grew 40% {words(n - 4)} done.</p>")
    assert len(c.paragraphs[0].split()) == n, c.paragraphs[0][:60]
    score, _, _ = run_method("answer_capsule", c)
    assert (score > 0) is ok


def test_answer_capsule_rejects_weak_openers():
    """A capsule that starts with 'However' depends on the paragraph before it."""
    strong = ctx("<p>Revenue grew 40% " + words(40) + " done.</p>")
    weak = ctx("<p>However revenue grew 40% " + words(40) + " done.</p>")
    assert run_method("answer_capsule", strong)[0] > 0
    assert run_method("answer_capsule", weak)[0] == 0


def test_answer_capsule_requires_terminal_punctuation():
    c = ctx("<p>Revenue grew 40% " + words(40) + " unfinished</p>")
    assert run_method("answer_capsule", c)[0] == 0


# ------------------------------------------------------ chunk_quotability 50-150

@pytest.mark.parametrize("n,ok", [(49, False), (50, True), (150, True), (151, False)])
def test_chunk_quotability_band(n, ok):
    c = ctx(f"<p>We measured 92% {words(n - 3)}</p>")
    assert len(c.paragraphs[0].split()) == n, c.paragraphs[0][:60]
    score, _, _ = run_method("chunk_quotability", c)
    assert (score > 0) is ok


# ------------------------------------------------------------ TTR 200/50 window

def test_ttr_needs_at_least_50_words():
    assert run_method("unique_words", ctx(f"<p>{words(40)}</p>"))[0] == 0


def test_ttr_detects_at_the_040_threshold():
    """All-identical words give TTR near 0; all-distinct gives 1.0."""
    repetitive = ctx("<p>" + words(200) + "</p>")
    varied = ctx("<p>" + distinct_words(200) + "</p>")
    assert run_method("unique_words", repetitive)[1] is False
    score, detected, _ = run_method("unique_words", varied)
    assert detected is True and score == 3


# --------------------------------------------------------- readability FK 6-8

def test_flesch_kincaid_formula_matches_the_published_definition():
    # 0.39*(W/S) + 11.8*(Syl/W) - 15.59
    assert cit.flesch_kincaid(100, 10, 150) == pytest.approx(0.39 * 10 + 11.8 * 1.5 - 15.59)
    assert cit.flesch_kincaid(0, 0, 0) == 0.0


@pytest.mark.parametrize("fk,expected", [
    (5.9, 3), (6.0, 5), (8.0, 5), (8.1, 3), (10.0, 3), (10.1, 1),
    (12.0, 1), (12.1, 0), (3.9, 0), (4.0, 1),
])
def test_readability_band_cutoffs(fk, expected):
    """Grade 6-8 full credit, 5-10 partial, 4-12 minimal — exact source boundaries."""
    assert cit.fk_band_score(fk) == expected


def test_readability_prefers_moderate_prose_over_dense_prose():
    dense = ctx("<p>" + " ".join(
        ["Notwithstanding institutional heterogeneity, multidimensional epistemological "
         "considerations necessitate comprehensive methodological reconsideration throughout "
         "contemporary organisational infrastructures."] * 10) + "</p>")
    moderate = ctx("<p>" + " ".join(
        ["The report shows that most teams publish content without a clear structure, "
         "which limits how often search engines select it."] * 10) + "</p>")
    assert run_method("readability", dense)[0] <= run_method("readability", moderate)[0]


# ------------------------------------------------------- keyword stuffing 2.5%

def test_keyword_stuffing_clean_text_scores_full():
    c = ctx("<p>" + distinct_words(300) + "</p>")
    assert run_method("keyword_stuffing", c)[0] == 6


def test_keyword_stuffing_is_detected_above_the_threshold():
    # 'widget' at ~10% of tokens, far over the 2.5% threshold
    body = ("widget " * 30 + distinct_words(270))
    score, detected, _ = run_method("keyword_stuffing", ctx(f"<p>{body}</p>"))
    assert detected is True and score < 6


def test_short_text_is_not_judged_for_stuffing():
    """Under 50 tokens the measure is meaningless, so the source returns full marks."""
    assert run_method("keyword_stuffing", ctx("<p>widget widget widget</p>"))[0] == 6


# ---------------------------------------------------------- neutral defaults

def test_no_images_is_neutral_not_zero():
    """geo-optimizer returns 3/5 when there are no images. Scoring 0 would punish
    a text page for something that is not a defect."""
    assert run_method("image_alt_quality", ctx("<p>text</p>"))[0] == 3


def test_no_internal_links_is_neutral():
    assert run_method("anchor_text_quality", ctx("<p>text</p>"))[0] == 2


def test_generic_anchor_text_scores_below_descriptive():
    generic = ctx('<a href="https://acme.example/a">click here</a>'
                  '<a href="https://acme.example/b">read more</a>')
    good = ctx('<a href="https://acme.example/a">2026 citation benchmarks</a>'
               '<a href="https://acme.example/b">schema implementation guide</a>')
    assert run_method("anchor_text_quality", generic)[0] < run_method("anchor_text_quality", good)[0]


def test_hreflang_absence_is_zero_but_not_a_penalty():
    score, detected, detail = run_method("international_geo", ctx("<p>text</p>"))
    assert score == 0 and detected is False and "not penalised" in detail


# ------------------------------------------------------------- alt text quality

@pytest.mark.parametrize("alt,descriptive", [
    ("image", False), ("logo", False), ("IMG_1234", False), ("photo", False),
    ("Citation rate by content length across 2026", True),
])
def test_generic_alt_text_is_not_descriptive(alt, descriptive):
    c = ctx(f'<img src="a.png" alt="{alt}">')
    score, _, _ = run_method("image_alt_quality", c)
    assert (score >= 5) is descriptive


# ------------------------------------------------------------------ crawl budget

def test_noindex_costs_two_points():
    assert run_method("crawl_budget", ctx('<meta name="robots" content="noindex">'))[0] == 1


def test_clean_page_keeps_full_crawl_budget():
    assert run_method("crawl_budget", ctx("<p>text</p>"))[0] == 3


# ----------------------------------------------------------------- resilience

def test_a_broken_method_does_not_sink_the_audit():
    """One method raising must degrade to zero, not fail the whole scan."""
    original = METHODS[0]
    def boom(c):
        raise ValueError("synthetic")
    METHODS[0] = (original[0], original[1], boom)
    try:
        result = cit.run(_FakeCtx(ctx("<p>text</p>")))
        assert result["methods"][0]["score"] == 0
        assert "error" in result["methods"][0]["detail"]
        assert result["max_possible"] == 210
    finally:
        METHODS[0] = original


def test_empty_page_scores_zero_without_crashing():
    result = cit.run(_FakeCtx(ctx("")))
    assert 0 <= result["score"] <= 100


def test_statistics_accept_locale_percent_formats():
    """German, French and Italian write "94 %" with a (non-breaking) space and a
    decimal comma. Matching only "94%" failed every translated page."""
    from audit.citability import STAT_RE

    for s in ["94%", "94 %", "94 %", "94 %", "3,5 %", "12.5%"]:
        assert STAT_RE.search(s), s
    assert not STAT_RE.search("version 4 of the plan")


def test_readability_is_not_scored_on_non_english_pages():
    """Flesch-Kincaid is English-only, so a German page is left out of the
    readability score rather than failed by it, and the maximum shrinks to match."""
    from dataclasses import replace
    from audit import Ctx, citability_engine
    from tests.test_audit import make_snapshot

    snap = make_snapshot("good.html")
    en = citability_engine.run(Ctx(snap))
    assert 'lang="en"' in snap.html
    de = citability_engine.run(Ctx(replace(snap, html=snap.html.replace('lang="en"', 'lang="de"', 1))))

    de_read = next(m for m in de["methods"] if m["name"] == "readability")
    assert de_read["max_score"] == 0 and "English-only" in de_read["detail"]
    assert de["max_possible"] == en["max_possible"] - 8


def test_citable_numbers_accept_european_formats():
    """Answer capsules need a citable figure. "94 %" and "5.000 €" are how German,
    French and Italian write them, and were invisible to the detector."""
    from audit.citability import CITABLE_NUMERIC_RE as R

    for s in ["94%", "94 %", "94 %", "€5,000", "5.000 €", "5.000 €", "2026"]:
        assert R.search(s), s


def test_decorative_images_are_left_out_of_alt_quality():
    """Only-decorative images score like no images: nothing to describe."""
    assert run_method("image_alt_quality", ctx('<img src="a.svg" alt="">'))[0] == 3
    assert run_method("image_alt_quality", ctx('<img src="a.png">'))[0] == 0
