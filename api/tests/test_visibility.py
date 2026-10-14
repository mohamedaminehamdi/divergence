"""Scoring tests against recorded engine payloads — no live API calls."""
import pytest

from visibility import aggregate
from visibility.engines import Anthropic, EngineResponse, Gemini, OpenAI, Perplexity
from visibility.score import _points, score_response

BRAND, DOMAIN = "Acme Analytics", "acme.example"


def resp(engine, prompt, answer, citations, error=None):
    return EngineResponse(engine, prompt, answer, citations, error)


# -------------------------------------------------------------- response parsing

def test_perplexity_parses_answer_and_citations():
    r = Perplexity()._parse("q", {
        "choices": [{"message": {"content": "Acme Analytics is a good option."}}],
        "citations": ["https://acme.example/pricing", "https://rival.com"],
    })
    assert r.answer.startswith("Acme")
    assert r.cited_domains == {"acme.example", "rival.com"}


def test_perplexity_falls_back_to_search_results():
    r = Perplexity()._parse("q", {
        "choices": [{"message": {"content": "hi"}}],
        "search_results": [{"url": "https://acme.example/a"}, {"url": ""}],
    })
    assert r.citations == ["https://acme.example/a"]


def test_openai_parses_url_citation_annotations():
    r = OpenAI()._parse("q", {"output": [{"content": [{
        "type": "output_text",
        "text": "Try Acme Analytics.",
        "annotations": [
            {"type": "url_citation", "url": "https://acme.example/"},
            {"type": "file_citation", "url": "https://ignored.com"},
        ],
    }]}]})
    assert r.answer == "Try Acme Analytics."
    assert r.cited_domains == {"acme.example"}


def test_anthropic_parses_text_citations_and_search_results():
    r = Anthropic()._parse("q", {"content": [
        {"type": "text", "text": "Acme Analytics leads. ", "citations": [{"url": "https://acme.example/x"}]},
        {"type": "web_search_tool_result", "content": [{"url": "https://rival.com/y"}]},
    ]})
    assert "Acme" in r.answer
    assert r.cited_domains == {"acme.example", "rival.com"}


def test_gemini_prefers_domain_title_over_redirect_uri():
    """Gemini's grounding uri is a vertexaisearch redirect; the title holds the real domain."""
    r = Gemini()._parse("q", {"candidates": [{
        "content": {"parts": [{"text": "Acme Analytics is popular."}]},
        "groundingMetadata": {"groundingChunks": [
            {"web": {"title": "acme.example", "uri": "https://vertexaisearch.cloud.google.com/redirect/abc"}},
            {"web": {"uri": "https://rival.com/post"}},
        ]},
    }]})
    assert r.cited_domains == {"acme.example", "rival.com"}


def test_engine_error_is_captured_not_raised():
    r = EngineResponse("openai", "q", error="HTTP 429")
    assert r.error and r.cited_domains == set()


# --------------------------------------------------------------- response scoring

def test_citation_beats_mention():
    cited = score_response(resp("openai", "q", "Use something.", ["https://acme.example/"]), BRAND, DOMAIN)
    mentioned = score_response(resp("openai", "q", "Use Acme Analytics.", ["https://rival.com"]), BRAND, DOMAIN)
    absent = score_response(resp("openai", "q", "Use Rival.", ["https://rival.com"]), BRAND, DOMAIN)
    assert _points(cited) > _points(mentioned) > _points(absent) == 0


def test_subdomain_counts_as_the_site():
    s = score_response(resp("openai", "q", "x", ["https://docs.acme.example/guide"]), BRAND, DOMAIN)
    assert s["cited"]


def test_lookalike_domain_does_not_count():
    s = score_response(resp("openai", "q", "x", ["https://notacme.example/"]), BRAND, DOMAIN)
    assert not s["cited"]


def test_www_is_normalised():
    s = score_response(resp("openai", "q", "x", ["https://www.acme.example/"]), BRAND, DOMAIN)
    assert s["cited"]


def test_brand_match_is_whole_word_and_case_insensitive():
    assert score_response(resp("e", "q", "we like acme analytics a lot", []), BRAND, DOMAIN)["mentioned"]
    assert not score_response(resp("e", "q", "AcmeAnalyticsPro is different", []), BRAND, DOMAIN)["mentioned"]


def test_mention_offset_and_excerpt_point_at_the_brand():
    s = score_response(resp("e", "q", "x" * 500 + " Acme Analytics wins.", []), BRAND, DOMAIN)
    assert s["first_mention_offset"] == 501
    assert "Acme Analytics" in s["answer_excerpt"]


# -------------------------------------------------------------------- aggregation

def test_aggregate_scores_and_share_of_voice():
    responses = [
        resp("perplexity", "best analytics", "Acme Analytics is great.", ["https://acme.example/", "https://rival.com"]),
        resp("perplexity", "cheapest analytics", "Rival is cheapest.", ["https://rival.com"]),
        resp("openai", "best analytics", "Acme Analytics is mentioned.", ["https://rival.com"]),
        resp("openai", "cheapest analytics", "Nothing relevant.", ["https://other.com"]),
    ]
    agg = aggregate(responses, BRAND, DOMAIN)
    assert agg["cited_count"] == 1
    assert agg["mentioned_count"] == 2
    assert agg["prompts_run"] == 2
    # 1 cited (1.0) + 1 mention-only (0.4) over 4 responses
    assert agg["overall"] == round(100 * 1.4 / 4)
    # own citations 1, competitors rival x3 + other x1 => 1/5
    assert agg["share_of_voice"] == 20.0
    assert agg["competitors"][0] == {"domain": "rival.com", "citations": 3, "share": 60.0}
    assert [e["engine"] for e in agg["engines"]] == ["perplexity", "openai"]


def test_failed_responses_excluded_from_denominator_not_hidden():
    responses = [
        resp("openai", "q1", "Acme Analytics.", ["https://acme.example/"]),
        resp("gemini", "q1", "", [], error="HTTP 429: rate limited"),
    ]
    agg = aggregate(responses, BRAND, DOMAIN)
    assert agg["overall"] == 100, "a rate-limited engine must not dilute the score"
    assert agg["responses_failed"] == 1 and agg["responses_ok"] == 1
    assert agg["errors"] == ["HTTP 429: rate limited"]
    assert "gemini" not in [e["engine"] for e in agg["engines"]]


def test_all_engines_failing_gives_zero_not_a_crash():
    agg = aggregate([resp("openai", "q", "", [], error="boom")], BRAND, DOMAIN)
    assert agg["overall"] == 0 and agg["share_of_voice"] == 0.0


def test_empty_response_set():
    agg = aggregate([], BRAND, DOMAIN)
    assert agg["overall"] == 0 and agg["competitors"] == []
