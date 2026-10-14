"""Each guardrail must (a) stay silent on a clean report and (b) actually fire.

A rule that never fires is indistinguishable from a rule that is broken, so
every one gets a crafted violating report as well as a clean one.
"""
import pytest

from audit import Ctx, analyse
from audit.guardrails import assert_clean, verify
from tests.test_audit import HOSTILE_ROBOTS, make_snapshot


def rules(report) -> set[str]:
    return {v.rule for v in verify(report)}


def base_report(**over) -> dict:
    r = {
        "findings": [],
        "seo": {"cap_reasons": []},
        "geo": {"cap_reasons": []},
        "divergence": {"headline": "", "summary": "", "contrasts": []},
        "promise": {"headline": "", "seo_now": 50, "seo_ceiling": 80,
                    "geo_now": 40, "geo_ceiling": 70},
        "disclaimer": "Scores are heuristics and not Google's own metrics.",
    }
    r.update(over)
    return r


def finding(**over) -> dict:
    f = {"id": "x", "title": "T", "passed": False, "severity": "medium",
         "evidence": "", "fix": None, "note": None, "seo_weight": 1.0, "geo_weight": 1.0,
         "advisory": False}
    f.update(over)
    return f


# ------------------------------------------------------------------ clean cases

@pytest.mark.parametrize("fixture,kw", [
    ("good.html", {}),
    ("bad.html", {"robots": HOSTILE_ROBOTS, "sitemap": False}),
    ("bad.html", {}),
])
def test_real_reports_are_clean(fixture, kw):
    assert_clean(analyse(Ctx(make_snapshot(fixture, **kw))))


def test_empty_report_only_complains_about_the_disclaimer():
    assert rules(base_report(disclaimer="")) == {"missing-disclaimer"}


# ------------------------------------------------------------- retired metrics

@pytest.mark.parametrize("text", [
    "Improve FID to under 100ms.",
    "First Input Delay is elevated.",
    "This fails Core Web Vitals 2.0.",
    "Your Visual Stability Index is poor.",
])
def test_retired_and_invented_metrics_are_caught(text):
    assert "banned-term" in rules(base_report(findings=[finding(evidence=text)]))


def test_inp_is_not_flagged():
    """INP is the live metric — the rule must not be a blanket ban on metric names."""
    assert "banned-term" not in rules(base_report(findings=[finding(evidence="Improve INP below 200ms.")]))


def test_fid_matches_on_word_boundary_only():
    assert "banned-term" not in rules(base_report(findings=[finding(evidence="We are confident in this.")]))


# ------------------------------------------------------------ deprecated schema

@pytest.mark.parametrize("t", ["HowTo", "ClaimReview", "VehicleListing", "EstimatedSalary"])
def test_recommending_deprecated_schema_is_caught(t):
    assert "deprecated-schema" in rules(
        base_report(findings=[finding(fix=f"Add {t} schema to this page.")]))


# -------------------------------------------------------------------- FAQPage

def test_faqpage_cannot_be_raised_above_info_when_it_is_the_subject():
    assert "faqpage-severity" in rules(base_report(findings=[
        finding(title="FAQPage schema missing", severity="high")]))


def test_recommending_faqpage_is_caught():
    assert "faqpage-recommended" in rules(base_report(findings=[
        finding(fix="Add FAQPage schema for rich results.")]))


def test_recommending_faqpage_removal_is_caught():
    assert "faqpage-removal" in rules(base_report(findings=[
        finding(fix="Remove FAQPage markup, it no longer does anything.")]))


def test_explaining_that_faqpage_is_retired_is_allowed():
    """The correct thing to say must not trip the rule."""
    assert not rules(base_report(findings=[finding(
        title="Add question-and-answer sections",
        severity="high",
        fix="This is content structure, not FAQPage schema — Google retired FAQ rich results.",
    )])) & {"faqpage-severity", "faqpage-recommended", "faqpage-removal"}


# ------------------------------------------------------------- crawler tokens

def test_training_only_bot_must_not_carry_weight():
    assert "training-bot-weighted" in rules(base_report(findings=[
        finding(id="robots_gptbot", seo_weight=2.0, geo_weight=3.0)]))


def test_training_only_bot_must_not_be_called_a_citability_lever():
    assert "training-bot-citability-claim" in rules(base_report(findings=[
        finding(id="robots_claudebot", seo_weight=0, geo_weight=0,
                evidence="Blocking this stops Claude citing you.")]))


def test_training_bot_with_the_correction_is_allowed():
    assert "training-bot-citability-claim" not in rules(base_report(findings=[
        finding(id="robots_gptbot", seo_weight=0, geo_weight=0,
                evidence="GPTBot governs training only. Blocking it is a licensing choice and "
                         "does NOT affect whether you can be cited.")]))


def test_real_audit_never_weights_a_training_bot():
    report = analyse(Ctx(make_snapshot("good.html")))
    training = [f for f in report["findings"]
                if f["id"] in ("robots_gptbot", "robots_claudebot")]
    assert training, "expected the training-bot checks to run"
    for f in training:
        assert f["seo_weight"] == 0 and f["geo_weight"] == 0
        assert f["audience"] == "neither"


# ------------------------------------------------------------------- llms.txt

def test_llms_txt_must_carry_zero_seo_weight():
    assert "llms-txt-seo-weight" in rules(base_report(findings=[
        finding(id="llms_txt", seo_weight=2.0)]))


def test_real_audit_gives_llms_txt_no_seo_weight():
    report = analyse(Ctx(make_snapshot("good.html")))
    llms = next(f for f in report["findings"] if f["id"] == "llms_txt")
    assert llms["seo_weight"] == 0.0


# ----------------------------------------------------------- sitemap and lazy

def test_recommending_priority_or_changefreq_is_caught():
    assert "sitemap-ignored-tags" in rules(base_report(findings=[
        finding(fix="Add <priority> and <changefreq> to every sitemap entry.")]))


def test_lazy_loader_false_positive_is_caught():
    assert "lazy-loader-false-positive" in rules(base_report(findings=[
        finding(id="lazy_loading", passed=False,
                evidence="A JavaScript lazy-loader is in use (lazysizes).")]))


def test_real_audit_does_not_flag_lazy_loading_when_a_loader_is_present():
    snap = make_snapshot("good.html")
    snap.html = snap.html.replace("<body>", "<body><script src='/lazysizes.min.js'></script>" +
                                  "".join(f"<img src='a{i}.jpg' alt='chart number {i} of results'>"
                                          for i in range(5)))
    report = analyse(Ctx(snap))
    lazy = next(f for f in report["findings"] if f["id"] == "lazy_loading")
    assert lazy["passed"], "must not flag lazy loading when a JS lazy-loader is detected"
    assert_clean(report)


# -------------------------------------------------------------------- promise

def test_promise_may_not_regress():
    assert "promise-regression" in rules(base_report(
        promise={"headline": "", "seo_now": 80, "seo_ceiling": 60,
                 "geo_now": 40, "geo_ceiling": 70}))


def test_promise_may_not_exceed_100():
    assert "promise-impossible" in rules(base_report(
        promise={"headline": "", "seo_now": 80, "seo_ceiling": 120,
                 "geo_now": 40, "geo_ceiling": 70}))


def test_real_promise_never_exceeds_the_ceiling_it_simulated():
    for fixture in ("good.html", "bad.html"):
        p = analyse(Ctx(make_snapshot(fixture)))["promise"]
        assert p["seo_ceiling"] >= p["seo_now"]
        assert p["geo_ceiling"] >= p["geo_now"]
        assert p["seo_ceiling"] <= 100 and p["geo_ceiling"] <= 100


# ------------------------------------------------------------------- backlinks

def test_backlink_gate_blocks_a_number_below_four_factors():
    assert "backlink-gate" in rules(base_report(backlinks={"factors_scored": 2, "score": 55}))


def test_backlink_gate_allows_not_assessed():
    assert "backlink-gate" not in rules(base_report(backlinks={"factors_scored": 2, "score": None}))


def test_backlink_gate_allows_a_number_at_four_factors():
    assert "backlink-gate" not in rules(base_report(backlinks={"factors_scored": 4, "score": 55}))


# ------------------------------------------------------------------ disclaimer

def test_disclaimer_is_required_and_must_say_heuristic():
    assert "missing-disclaimer" in rules(base_report(disclaimer="Scores computed from this page."))
    assert "missing-disclaimer" not in rules(base_report())


# ------------------------------------------------------------------ advisories

def test_advisory_carrying_weight_is_caught():
    assert "advisory-weighted" in rules(base_report(findings=[
        finding(id="cit_answer_first", advisory=True, seo_weight=1.0, geo_weight=1.0)]))


def test_real_citability_advisories_carry_no_weight():
    """Regression: apply_weights used to overwrite these with the generic default,
    double-counting citability in both category scores."""
    report = analyse(Ctx(make_snapshot("good.html")))
    advisories = [f for f in report["findings"] if f.get("advisory")]
    assert advisories, "expected citability advisories on this fixture"
    for f in advisories:
        assert f["seo_weight"] == 0 and f["geo_weight"] == 0, f
        assert f["audience"] == "ai"
    assert_clean(report)


def test_advisories_keep_their_declared_effort():
    report = analyse(Ctx(make_snapshot("good.html")))
    efforts = {f["effort"] for f in report["findings"] if f.get("advisory")}
    assert efforts - {"hours"}, "advisories must keep their own effort, not the default"


# ------------------------------------------------------------------ typography

@pytest.mark.parametrize("text", ["Fix this — it matters.", "Range 2018–2026."])
def test_em_and_en_dashes_are_caught(text):
    assert "dash-typography" in rules(base_report(findings=[finding(evidence=text)]))


def test_plain_hyphen_is_allowed():
    assert "dash-typography" not in rules(base_report(findings=[finding(evidence="Target 50-60 chars.")]))


def test_no_dashes_in_any_real_report():
    """Every rendered string across both fixtures, including generated fixes."""
    for fixture in ("good.html", "bad.html", "docs_geo_ahead.html"):
        report = analyse(Ctx(make_snapshot(fixture)))
        assert "dash-typography" not in rules(report), [
            v for v in verify(report) if v.rule == "dash-typography"
        ][:3]


def test_dash_rule_exempts_quoted_page_content():
    """A scanned site's own title is evidence, not our prose. Rewriting it would
    misreport what the page actually says."""
    quoted = finding(evidence='Title is 38 characters: "Ahrefs Blog — SEO insights". Target 50-60.')
    assert "dash-typography" not in rules(base_report(findings=[quoted]))


def test_dash_rule_still_fires_outside_quotes():
    mixed = finding(evidence='Title reads "Fine — here" but this sentence — ours — is not quoted.')
    assert "dash-typography" in rules(base_report(findings=[mixed]))
