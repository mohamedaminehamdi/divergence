"""Per-check weighting for the two scores — the divergence table.

This file IS the product's thesis. Every check declares what it is worth to a
search crawler and what it is worth to an answer engine, and those numbers are
frequently different. The report's contrast view is generated from the gaps
here, so it stays correct automatically as checks are added.

A weight of 0.0 means "genuinely does not matter to this audience" — not
"unknown". Several zeroes are load-bearing and sourced:
  * llms.txt has zero SEO weight: Google states it ignores the file entirely.
  * FAQPage has zero SEO weight: Google retired FAQ rich results for all sites.
  * Training-only crawler tokens have zero weight on BOTH sides: blocking
    GPTBot does not affect ChatGPT *citability* (that is OAI-SearchBot) and
    Google-Extended governs Gemini training, not AI Overviews eligibility.
    Scoring them would be the exact error both source repos warn against.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import bots
from .taxonomy import (
    ACCESSIBILITY, AI_READINESS, AUTHORITY, CITABILITY, CONTENT, EFFORT_DAYS,
    EFFORT_HOURS, EFFORT_MINUTES, EFFORT_WEEKS, IMAGES, MULTIMODAL, ONPAGE,
    PERFORMANCE, SCHEMA, STRUCTURAL, TECHNICAL,
)


@dataclass(frozen=True)
class Weighting:
    seo_category: str | None = None
    seo_weight: float = 0.0
    geo_dimension: str | None = None
    geo_weight: float = 0.0
    effort: str = EFFORT_HOURS
    note: str | None = None   # shown in the contrast view when the weights diverge

    @property
    def divergence(self) -> float:
        """Signed gap. Positive = matters more to search, negative = more to AI."""
        return self.seo_weight - self.geo_weight


DEFAULT = Weighting(seo_category=CONTENT, seo_weight=1.0, geo_dimension=STRUCTURAL, geo_weight=1.0)

TABLE: dict[str, Weighting] = {
    # ---------------------------------------------------------- crawler access
    "edge_block": Weighting(
        TECHNICAL, 3.0, ACCESSIBILITY, 3.0, EFFORT_MINUTES,
        "A WAF blocking bots costs you both audiences equally.",
    ),
    "no_js_content": Weighting(
        TECHNICAL, 1.0, ACCESSIBILITY, 3.0, EFFORT_WEEKS,
        "Googlebot executes JavaScript. No answer engine does, so a client-rendered "
        "page can rank on Google and be completely invisible to AI.",
    ),
    # --------------------------------------------------------- discovery files
    "llms_txt": Weighting(
        None, 0.0, ACCESSIBILITY, 0.5, EFFORT_MINUTES,
        "Google states it ignores llms.txt outright. Presence-only signal for AI, "
        "and worth nothing at all for search.",
    ),
    # ---------------------------------------------------- content quality
    "filler_content": Weighting(
        CONTENT, 1.0, CITABILITY, 2.5, EFFORT_HOURS,
        "Padding costs a little ranking and a lot of citability: an engine lifting a quote has "
        "to find one first.",
    ),
    "ai_phrasing": Weighting(
        CONTENT, 1.0, CITABILITY, 2.0, EFFORT_HOURS,
        "Google's scaled-content-abuse guidance targets unedited generated drafts; answer "
        "engines simply find nothing quotable in them.",
    ),
    "information_density": Weighting(
        CONTENT, 1.5, CITABILITY, 3.0, EFFORT_DAYS,
        "Specificity is the single strongest citability signal. Search tolerates generic prose "
        "that ranks on links; an answer engine has nothing to extract from it.",
    ),
    # --------------------------------------------------------- agent access
    "semantic_landmarks": Weighting(
        STRUCTURAL, 1.0, STRUCTURAL, 2.5, EFFORT_HOURS,
        "Googlebot infers the main content from layout heuristics it has refined for years. An "
        "answer engine reads the tags, and without <main> it quotes your navigation.",
    ),
    "real_controls": Weighting(
        ACCESSIBILITY, 0.5, ACCESSIBILITY, 1.5, EFFORT_HOURS,
        "A click-handler div is invisible to any agent trying to act on the page.",
    ),
    "labelled_inputs": Weighting(
        ACCESSIBILITY, 0.5, ACCESSIBILITY, 1.5, EFFORT_HOURS,
        "An agent completing your form needs to know what each field wants.",
    ),
    "content_signal": Weighting(
        None, 0.0, AI_READINESS, 1.0, EFFORT_MINUTES,
        "Content-Signal is an AI-usage declaration. Search crawlers ignore it entirely, "
        "so it is worth nothing to Google and is pure answer-engine signal.",
    ),
    "markdown_alt": Weighting(
        None, 0.0, ACCESSIBILITY, 1.0, EFFORT_HOURS,
        "A markdown twin exists for machine readers. Google indexes the HTML and gains "
        "nothing; an answer engine parses it far more reliably.",
    ),
    "sitemap": Weighting(
        TECHNICAL, 2.0, ACCESSIBILITY, 0.5, EFFORT_MINUTES,
        "A sitemap is core crawl infrastructure for search; answer engines lean on it far less.",
    ),
    # ------------------------------------------------------------------ schema
    "jsonld_present": Weighting(SCHEMA, 2.0, AUTHORITY, 1.5, EFFORT_HOURS),
    "entity_schema": Weighting(
        SCHEMA, 1.5, AUTHORITY, 2.5, EFFORT_HOURS,
        "sameAs entity links tie you to a knowledge graph, which is how an answer engine "
        "confirms you are who you claim to be.",
    ),
    "page_type_schema": Weighting(SCHEMA, 1.5, AUTHORITY, 1.0, EFFORT_HOURS),
    "schema_fields": Weighting(SCHEMA, 1.5, AUTHORITY, 1.0, EFFORT_HOURS),
    # ----------------------------------------------------------------- on-page
    "canonical": Weighting(
        ONPAGE, 2.0, ACCESSIBILITY, 0.5, EFFORT_MINUTES,
        "Duplicate-URL control is a search-ranking concern far more than a citation one.",
    ),
    "meta_description": Weighting(
        ONPAGE, 1.5, STRUCTURAL, 0.5, EFFORT_MINUTES,
        "Drives click-through on a SERP. Answer engines rarely surface it.",
    ),
    "single_h1": Weighting(ONPAGE, 1.5, STRUCTURAL, 1.0, EFFORT_MINUTES),
    "heading_hierarchy": Weighting(
        ONPAGE, 1.0, STRUCTURAL, 2.0, EFFORT_HOURS,
        "Headings are the chunk boundaries a retriever splits on, so hierarchy "
        "matters more to AI than to a crawler that reads the whole document.",
    ),
    # -------------------------------------------------- answer-engine specific
    "question_headings": Weighting(
        ONPAGE, 0.5, STRUCTURAL, 2.0, EFFORT_DAYS,
        "\"Features\" ranks fine. It matches nothing anyone actually asks an assistant.",
    ),
    "answer_first": Weighting(
        None, 0.0, CITABILITY, 3.0, EFFORT_DAYS,
        "A self-contained answer in the first sentence is what gets lifted into a "
        "generated response. It has essentially no bearing on ranking.",
    ),
    "chunkability": Weighting(
        None, 0.0, STRUCTURAL, 2.0, EFFORT_DAYS,
        "Section length decides how cleanly you are retrieved. A crawler does not care.",
    ),
    "extractable_formats": Weighting(
        CONTENT, 1.0, CITABILITY, 2.0, EFFORT_DAYS,
        "Lists and tables are quoted far out of proportion to how often they appear.",
    ),
    "statistics": Weighting(
        CONTENT, 1.0, CITABILITY, 2.5, EFFORT_DAYS,
        "Specific numbers are what an engine can cite you AS THE SOURCE OF.",
    ),
    "outbound_citations": Weighting(CONTENT, 1.0, CITABILITY, 1.5, EFFORT_HOURS),
    # ------------------------------------------------------------ trust/E-E-A-T
    "named_author": Weighting(
        CONTENT, 2.0, AUTHORITY, 2.0, EFFORT_HOURS,
        "Trust is the heaviest E-E-A-T factor for search and the strongest authority "
        "signal for AI. One of the few things both audiences weight the same.",
    ),
    "visible_dates": Weighting(
        CONTENT, 1.5, AUTHORITY, 2.0, EFFORT_MINUTES,
        "Content under 3 months old is ~3x more likely to be cited by an answer engine.",
    ),
    "about_contact": Weighting(CONTENT, 1.0, AUTHORITY, 1.0, EFFORT_HOURS),
    "freshness": Weighting(CONTENT, 1.0, AUTHORITY, 1.5, EFFORT_DAYS),
    # ------------------------------------------------------------- performance
    "delivery_speed": Weighting(
        PERFORMANCE, 2.0, ACCESSIBILITY, 0.5, EFFORT_DAYS,
        "Core Web Vitals are a confirmed ranking tiebreaker. Answer engines do not "
        "measure page speed at all. They only need the fetch to succeed.",
    ),

    # ------------------------------------------------- on-page (search-skewed)
    "title_length": Weighting(
        ONPAGE, 3.0, STRUCTURAL, 0.5, EFFORT_MINUTES,
        "The title is the strongest on-page ranking signal. An answer engine reads "
        "the whole document and barely weights it.",
    ),
    "meta_desc_length": Weighting(
        ONPAGE, 2.0, None, 0.0, EFFORT_MINUTES,
        "Drives click-through from a results page. There is no results page in a "
        "generated answer, so it is worth nothing there.",
    ),
    "url_length": Weighting(ONPAGE, 1.0, None, 0.0, EFFORT_HOURS),
    "twitter_card": Weighting(ONPAGE, 0.5, None, 0.0, EFFORT_MINUTES),
    "breadcrumbs": Weighting(ONPAGE, 1.5, STRUCTURAL, 0.5, EFFORT_HOURS),
    "internal_links": Weighting(
        ONPAGE, 2.5, STRUCTURAL, 0.5, EFFORT_DAYS,
        "Internal links are how crawl equity moves through a site. An answer engine "
        "retrieves a passage, not a link graph.",
    ),
    # ----------------------------------------------------------------- technical
    "https": Weighting(TECHNICAL, 3.0, ACCESSIBILITY, 1.0, EFFORT_HOURS),
    "security_headers": Weighting(
        TECHNICAL, 0.5, None, 0.0, EFFORT_HOURS,
        "Deliberately light: only Core Web Vitals feed ranking directly, and HTTPS "
        "itself is confirmed but lightweight.",
    ),
    "viewport": Weighting(
        TECHNICAL, 2.5, None, 0.0, EFFORT_MINUTES,
        "Indexing is mobile-first, so a missing viewport is a real ranking problem. "
        "Answer engines never render the page at all.",
    ),
    "indexable": Weighting(
        TECHNICAL, 3.0, ACCESSIBILITY, 2.0, EFFORT_MINUTES,
        "noindex removes the page from search outright, and AI Overviews require an "
        "indexed, snippet-eligible page.",
    ),
    # -------------------------------------------------------------------- images
    "image_alt": Weighting(IMAGES, 3.0, MULTIMODAL, 2.0, EFFORT_HOURS),
    "image_dims": Weighting(
        IMAGES, 2.0, None, 0.0, EFFORT_HOURS,
        "Prevents layout shift, which is a Core Web Vitals ranking input. Invisible to AI.",
    ),
    "image_formats": Weighting(IMAGES, 1.5, None, 0.0, EFFORT_HOURS),
    "lazy_loading": Weighting(IMAGES, 1.0, None, 0.0, EFFORT_HOURS),
    # ------------------------------------------------------------------- content
    "word_count": Weighting(CONTENT, 2.0, STRUCTURAL, 1.0, EFFORT_DAYS),
    "readability_ease": Weighting(
        CONTENT, 1.0, None, 0.0, EFFORT_DAYS,
        "Scored on the search side only. The citability engine already measures "
        "readability for AI, and counting it twice would double-penalise.",
    ),
    "content_padding": Weighting(
        CONTENT, 2.5, STRUCTURAL, 1.0, EFFORT_DAYS,
        "Padding and LLM-tell phrasing read as low-value content to a quality rater.",
    ),
    "info_density": Weighting(CONTENT, 2.0, STRUCTURAL, 1.5, EFFORT_DAYS),
    # --------------------------------------------------------------- performance
    "dom_size": Weighting(
        PERFORMANCE, 1.5, None, 0.0, EFFORT_WEEKS,
        "A heavy DOM hurts INP, a ranking input. Answer engines parse the HTML and "
        "never measure interaction.",
    ),
    "render_blocking": Weighting(PERFORMANCE, 2.5, None, 0.0, EFFORT_HOURS),
    "font_display": Weighting(PERFORMANCE, 1.0, None, 0.0, EFFORT_MINUTES),
    # -------------------------------------------------------------- multi-modal
    "multimodal": Weighting(
        CONTENT, 1.0, MULTIMODAL, 3.0, EFFORT_DAYS,
        "Pages mixing text, tables and media are selected by answer engines far more "
        "often than text-only pages.",
    ),
    "media_transcripts": Weighting(
        CONTENT, 0.5, MULTIMODAL, 2.0, EFFORT_DAYS,
        "An answer engine cannot watch a video. The transcript is the only citable part.",
    ),
}


def for_robots_check(bot: str) -> Weighting:
    """robots.txt checks are generated per bot, so their weights are derived.

    The tier decides everything, and this is where the most-misunderstood rule in
    AI SEO lives: a blocked *training* crawler costs you nothing in either score.
    """
    tier = bots.tier(bot)
    if bot == "Googlebot":
        return Weighting(
            TECHNICAL, 3.0, ACCESSIBILITY, 3.0, EFFORT_MINUTES,
            "Googlebot feeds Search AND AI Overviews. Blocking it costs you both.",
        )
    if bot in bots.CITATION_BOTS:
        return Weighting(
            AI_READINESS, 1.0, ACCESSIBILITY, 3.0, EFFORT_MINUTES,
            f"{bot} decides whether this engine can cite you. Blocking it removes you "
            "from its answers entirely.",
        )
    if tier == "training":
        return Weighting(
            None, 0.0, None, 0.0, EFFORT_MINUTES,
            f"{bot} governs model training only. Blocking it is a licensing choice and "
            "does NOT affect whether you can be cited. That is a different token.",
        )
    if tier == "search":
        return Weighting(AI_READINESS, 0.5, ACCESSIBILITY, 1.0, EFFORT_MINUTES)
    return Weighting(None, 0.0, None, 0.0, EFFORT_MINUTES)


def lookup(check_id: str) -> Weighting:
    if check_id.startswith("robots_"):
        slug = check_id.removeprefix("robots_")
        for bot in bots.BOTS:
            if bot.lower().replace("-", "_") == slug:
                return for_robots_check(bot)
    return TABLE.get(check_id, DEFAULT)
