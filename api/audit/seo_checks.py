"""Classic SEO checks — the crawler-facing half of the score.

Thresholds come from claude-seo's quality-gates and per-skill rubrics. Several
carry deliberate restraint the source insists on and that naive auditors get
wrong; those are commented where they apply.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .checks import CONTENT as _C
from .checks import Ctx, Finding, check
from .citability import _syllables

# ---------------------------------------------------------------- claude-seo data

FILLER_PHRASES = (
    "it's important to note that", "in this article, we'll explore",
    "in this article we will explore", "in today's fast-paced world",
    "in today's digital age", "in today's competitive landscape", "needless to say",
    "at the end of the day", "when it comes to", "when all is said and done",
    "in the realm of", "in the world of", "the bottom line is", "without further ado",
    "first and foremost", "last but not least", "for what it's worth",
    "it goes without saying", "as we all know", "the truth is that",
    "the fact of the matter is", "more often than not", "let's dive in",
    "let's dive into", "let's take a closer look", "let's take a deeper look",
)

AI_PATTERNS = (
    "delve into", "delve deeper into", "in the ever-evolving", "ever-evolving landscape",
    "ever-changing landscape", "in the dynamic landscape", "navigating the",
    "navigate the complexities", "tapestry of", "rich tapestry", "intricate tapestry",
    "embark on a journey", "embarking on this", "a testament to", "a beacon of",
    "the cornerstone of", "a cornerstone of", "at the heart of", "at its core",
    "in essence,", "in conclusion,", "ultimately,", "moreover,", "furthermore,",
    "however, it's worth noting", "it's worth noting that", "by leveraging",
    "leverage the power of", "leveraging the power of", "harness the power of",
    "unlock the potential", "unlock the full potential", "the realm of possibilities",
    "open up a world of", "a world of possibilities", "elevate your", "transform your",
    "revolutionize the way", "game-changer", "game-changing", "cutting-edge",
    "state-of-the-art", "in summary,", "to summarize,", "to put it simply,",
    "in a nutshell,",
)

TITLE_MIN, TITLE_MAX = 50, 60
DESC_MIN, DESC_MAX = 150, 160
URL_MAX = 100
ALT_MIN, ALT_MAX = 10, 125
DOM_MAX = 1500
WORD_FLOOR = 300

SECURITY_HEADERS = (
    "content-security-policy", "strict-transport-security",
    "x-content-type-options", "referrer-policy",
)

# Third-party lazy-loaders strip loading="lazy" on purpose. Flagging those pages
# as "not lazy-loaded" is a false positive claude-seo calls out explicitly.
LAZY_LOADER_MARKERS = ("perfmatters", "ewww", "lazysizes", "lazyload", "data-src", "data-lazy")


# --------------------------------------------------------------------- on-page

@check
def title_length(c: Ctx) -> Finding:
    t = c.title
    n = len(t)
    ok = TITLE_MIN <= n <= TITLE_MAX
    evidence = (
        f'Title is {n} characters: "{t[:70]}".' + ("" if ok else f" Target {TITLE_MIN}-{TITLE_MAX}.")
        if t else "No <title> tag. This is the strongest single on-page signal."
    )
    return Finding(
        "title_length", _C, "Title tag length", ok, "high" if not t else "medium", evidence,
        None if ok else (
            f"Rewrite the title to {TITLE_MIN}-{TITLE_MAX} characters, primary keyword near the "
            "front, brand at the end:\n\n  <title>Primary Keyword: Specific Benefit | Brand</title>\n\n"
            + ("Currently too long. It will be truncated in results."
               if n > TITLE_MAX else "Currently too short. You are leaving relevance unclaimed.")
        ),
    )


@check
def meta_description_length(c: Ctx) -> Finding:
    d = c.meta("description") or ""
    n = len(d)
    ok = DESC_MIN <= n <= DESC_MAX
    return Finding(
        "meta_desc_length", _C, "Meta description length", ok, "medium",
        f"Meta description is {n} characters." + ("" if ok else f" Target {DESC_MIN}-{DESC_MAX}."),
        None if ok else (
            f'<meta name="description" content="A {DESC_MIN}-{DESC_MAX} character summary that '
            'answers the page\'s core question and gives a reason to click." />'
        ),
    )


@check
def url_length(c: Ctx) -> Finding:
    n = len(c.snap.final_url)
    ok = n <= URL_MAX
    return Finding(
        "url_length", _C, "URL length and shape", ok, "low",
        f"URL is {n} characters." + ("" if ok else f" Over the {URL_MAX}-character guideline."),
        None if ok else (
            f"Shorten the URL. Current path: {urlparse(c.snap.final_url).path}\n"
            "Use short, hyphenated, lowercase segments and no tracking parameters."
        ),
    )


@check
def twitter_card(c: Ctx) -> Finding:
    ok = c.meta("twitter:card") is not None
    return Finding(
        "twitter_card", _C, "Twitter Card tags", ok, "low",
        "Twitter Card present." if ok else "No twitter:card tag. Links share without a rich preview.",
        None if ok else (
            '<meta name="twitter:card" content="summary_large_image" />\n'
            '<meta name="twitter:title" content="..." />\n'
            '<meta name="twitter:description" content="..." />'
        ),
    )


@check
def breadcrumbs(c: Ctx) -> Finding:
    ok = "BreadcrumbList" in c.schema_types() or \
        c.tree.css_first('[class*=breadcrumb], nav[aria-label*="readcrumb"]') is not None
    return Finding(
        "breadcrumbs", _C, "Breadcrumb navigation", ok, "low",
        "Breadcrumbs present." if ok else "No breadcrumbs. They clarify hierarchy for crawlers and users.",
        None if ok else (
            '<script type="application/ld+json">\n{\n  "@context": "https://schema.org",\n'
            '  "@type": "BreadcrumbList",\n  "itemListElement": [\n'
            '    {"@type":"ListItem","position":1,"name":"Home","item":"/"},\n'
            '    {"@type":"ListItem","position":2,"name":"Section","item":"/section"}\n  ]\n}\n</script>'
        ),
    )


@check
def internal_linking(c: Ctx) -> Finding:
    n = len(c.internal_links)
    per_1k = n / max(len(c.words), 1) * 1000
    ok = n >= 3
    return Finding(
        "internal_links", _C, "Internal links", ok, "medium",
        f"{n} internal links ({per_1k:.1f} per 1,000 words)."
        + ("" if ok else " Thin internal linking limits how crawlers discover and weight your pages."),
        None if ok else (
            "Add 3-5 contextual internal links per 1,000 words, in the body rather than the nav,\n"
            "with anchor text that names the target page's topic."
        ),
    )


# ------------------------------------------------------------------- technical

@check
def https_enabled(c: Ctx) -> Finding:
    ok = c.snap.final_url.startswith("https://")
    return Finding(
        "https", _C, "HTTPS", ok, "critical",
        "Served over HTTPS." if ok else
        "Served over plain HTTP. This is a confirmed ranking signal and browsers mark the page insecure.",
        None if ok else "Install a TLS certificate and 301-redirect all HTTP traffic to HTTPS.",
    )


@check
def security_headers(c: Ctx) -> Finding:
    present = [h for h in SECURITY_HEADERS if h in c.snap.headers]
    missing = [h for h in SECURITY_HEADERS if h not in c.snap.headers]
    ok = len(present) >= 2
    # claude-seo is explicit that these are lightweight: only CWV feeds ranking
    # directly, so this stays low severity however many are missing.
    return Finding(
        "security_headers", _C, "Security headers", ok, "low",
        f"{len(present)} of {len(SECURITY_HEADERS)} security headers present."
        + (f" Missing: {', '.join(missing)}." if missing else ""),
        None if ok else (
            "Add to your server or CDN config:\n\n"
            "  Strict-Transport-Security: max-age=31536000; includeSubDomains\n"
            "  X-Content-Type-Options: nosniff\n"
            "  Referrer-Policy: strict-origin-when-cross-origin\n\n"
            "Worth doing, but a minor ranking factor. Do not prioritise it over content or speed."
        ),
    )


@check
def viewport_meta(c: Ctx) -> Finding:
    ok = c.meta("viewport") is not None
    return Finding(
        "viewport", _C, "Mobile viewport", ok, "high",
        "Viewport meta tag present." if ok else
        "No viewport meta tag. The page will not render correctly on mobile, and indexing is mobile-first.",
        None if ok else '<meta name="viewport" content="width=device-width, initial-scale=1" />',
    )


@check
def indexable(c: Ctx) -> Finding:
    robots = (c.meta("robots") or "").lower()
    xrobots = c.snap.headers.get("x-robots-tag", "").lower()
    blocked = "noindex" in robots or "noindex" in xrobots
    return Finding(
        "indexable", _C, "Page is indexable", not blocked, "critical",
        "No noindex directive." if not blocked else
        f"This page is set to noindex "
        f"({'meta robots' if 'noindex' in robots else 'X-Robots-Tag header'}). It cannot rank at all.",
        None if not blocked else
        'Remove the noindex directive if this page is meant to rank:\n'
        '  <meta name="robots" content="index, follow" />',
    )


# ---------------------------------------------------------------------- images

@check
def image_alt_text(c: Ctx) -> Finding:
    imgs = c.tree.css("img")
    if not imgs:
        return Finding("image_alt", _C, "Image alt text", True, "low", "No images on this page.")
    alts = [(i.attributes.get("alt") or "").strip() for i in imgs]
    missing = [a for a in alts if not a]
    bad_len = [a for a in alts if a and not (ALT_MIN <= len(a) <= ALT_MAX)]
    ok = not missing and len(bad_len) <= len(imgs) // 2
    return Finding(
        "image_alt", _C, "Image alt text", ok, "medium",
        f"{len(imgs)} images, {len(missing)} with no alt, {len(bad_len)} outside the "
        f"{ALT_MIN}-{ALT_MAX} character range.",
        None if ok else (
            f"Give every non-decorative image alt text of {ALT_MIN}-{ALT_MAX} characters describing "
            'what it shows. Decorative images get alt="".\n\n'
            '  <img src="chart.webp" alt="Citation rate by content length, 2020-2026" />'
        ),
    )


@check
def image_dimensions(c: Ctx) -> Finding:
    imgs = c.tree.css("img")
    if not imgs:
        return Finding("image_dims", _C, "Image dimensions set", True, "low", "No images on this page.")
    sized = [i for i in imgs
             if (i.attributes.get("width") and i.attributes.get("height"))
             or "aspect-ratio" in (i.attributes.get("style") or "")]
    ok = len(sized) >= len(imgs) * 0.8
    return Finding(
        "image_dims", _C, "Image dimensions set", ok, "medium",
        f"{len(sized)}/{len(imgs)} images declare width and height."
        + ("" if ok else " Undeclared dimensions cause layout shift, which hurts CLS."),
        None if ok else (
            "Add width and height to every <img>, or set CSS aspect-ratio:\n\n"
            '  <img src="hero.webp" width="1200" height="630" alt="..." />'
        ),
    )


@check
def image_formats(c: Ctx) -> Finding:
    imgs = c.tree.css("img")
    if not imgs:
        return Finding("image_formats", _C, "Modern image formats", True, "low", "No images on this page.")
    srcs = [(i.attributes.get("src") or "").lower() for i in imgs]
    legacy = [s for s in srcs if re.search(r"\.(jpe?g|png)(\?|$)", s)]
    responsive = sum(1 for i in imgs if i.attributes.get("srcset"))
    ok = len(legacy) <= len(imgs) * 0.3
    return Finding(
        "image_formats", _C, "Modern image formats", ok, "low",
        f"{len(legacy)}/{len(imgs)} images use JPEG/PNG; {responsive} use srcset.",
        None if ok else (
            "Serve WebP or AVIF with a fallback chain, and add srcset for responsive sizes:\n\n"
            "  <picture>\n    <source srcset='hero.avif' type='image/avif'>\n"
            "    <source srcset='hero.webp' type='image/webp'>\n"
            "    <img src='hero.jpg' width='1200' height='630' alt='...'>\n  </picture>"
        ),
    )


@check
def lazy_loading(c: Ctx) -> Finding:
    imgs = c.tree.css("img")
    if len(imgs) < 4:
        return Finding("lazy_loading", _C, "Lazy loading below the fold", True, "low",
                       "Too few images to need lazy loading.")
    html_lower = c.snap.html.lower()
    loader = next((m for m in LAZY_LOADER_MARKERS if m in html_lower), None)
    if loader:
        # claude-seo rule: never flag this when a JS lazy-loader is detected.
        return Finding(
            "lazy_loading", _C, "Lazy loading below the fold", True, "low",
            f'A JavaScript lazy-loader is in use ({loader}); native loading="lazy" is intentionally '
            "stripped by these plugins, so this is correct as-is.",
        )
    lazy = sum(1 for i in imgs if i.attributes.get("loading") == "lazy")
    ok = lazy >= 1
    return Finding(
        "lazy_loading", _C, "Lazy loading below the fold", ok, "low",
        f'{lazy}/{len(imgs)} images use loading="lazy".',
        None if ok else (
            'Add loading="lazy" to below-the-fold images only. Never on the LCP or hero image.\n'
            'that one should carry fetchpriority="high" instead.'
        ),
    )


# --------------------------------------------------------------------- content

@check
def word_count_floor(c: Ctx) -> Finding:
    n = len(c.words)
    ok = n >= WORD_FLOOR
    return Finding(
        "word_count", _C, "Content depth", ok, "medium",
        f"{n} words of body content."
        + ("" if ok else f" Below the {WORD_FLOOR}-word floor for a substantive page."),
        None if ok else (
            f"Expand to at least {WORD_FLOOR} words of genuinely useful content. This is a coverage\n"
            "floor, not a target. Word count is not a ranking factor, but a page this thin rarely\n"
            "covers a topic well enough to rank or to be cited."
        ),
    )


@check
def readability_ease(c: Ctx) -> Finding:
    # Flesch Reading Ease is an English formula, so for other languages it is not
    # measured, following this check's existing "cannot measure" convention.
    if c.lang not in ("", "en"):
        return Finding("readability_ease", _C, "Reading ease", True, "low",
                       f"Not measured: Flesch Reading Ease is English-only and this page is '{c.lang}'.")
    sents = [s for s in re.split(r"(?<=[.!?])\s+", c.body_text) if s.strip()]
    words = [w for w in c.words if w.isalpha()]
    if len(words) < 100 or not sents:
        return Finding("readability_ease", _C, "Reading ease", True, "low",
                       "Not enough prose to measure reading ease.")
    syl = sum(_syllables(w) for w in words)
    ease = 206.835 - 1.015 * (len(words) / len(sents)) - 84.6 * (syl / len(words))
    avg_sentence = len(words) / len(sents)
    ok = 60 <= ease <= 80 and avg_sentence <= 20
    return Finding(
        "readability_ease", _C, "Reading ease", ok, "low",
        f"Flesch Reading Ease {ease:.0f}, average sentence {avg_sentence:.0f} words. "
        "Target 60-70 for a general audience.",
        None if ok else (
            "Shorten sentences to 15-20 words and prefer common words.\n"
            "Note: readability is not a Google ranking factor. This is a comprehension check, "
            "not a penalty."
        ),
    )


@check
def filler_and_ai_phrasing(c: Ctx) -> Finding:
    """Ported from claude-seo's content_quality.py scoring."""
    text = c.body_text.lower()
    tokens = max(len(c.words), 1)
    filler_hits = sum(text.count(p) for p in FILLER_PHRASES)
    ai_hits = sum(text.count(p) for p in AI_PATTERNS)
    filler_score = min(100, round(filler_hits / tokens * 1000 * 25))
    ai_score = min(100, round(ai_hits / tokens * 1000 * 15))
    ok = filler_score < 50 and ai_score < 40
    found = [p for p in AI_PATTERNS if p in text][:5]
    return Finding(
        "content_padding", _C, "Padding and AI-typical phrasing", ok, "medium",
        f"{filler_hits} filler phrases, {ai_hits} AI-typical phrases "
        f"(filler score {filler_score}, AI score {ai_score})."
        + (f' Found: {", ".join(repr(f) for f in found)}.' if found else ""),
        None if ok else (
            "Cut padding and LLM-tell phrasing. Replace with specifics:\n"
            '  "in today\'s fast-paced world"  -> delete\n'
            '  "delve into"                    -> "examine"\n'
            '  "a testament to"                -> state the evidence\n'
            '  "leverage the power of"         -> "use"\n\n'
            "This is a quality heuristic, not an AI-detection claim. Statistical watermarks are "
            "not detectable and this does not attempt to detect them."
        ),
    )


@check
def information_density(c: Ctx) -> Finding:
    """(entities + numbers) per 100 tokens / 10, capped at 1.0, per claude-seo's formula."""
    tokens = max(len(c.words), 1)
    entities = len(re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", c.body_text))
    numbers = len(re.findall(r"\b\d+(?:[.,]\d+)?(?:%|st|nd|rd|th)?\b", c.body_text))
    density = min(1.0, (entities + numbers) * 100 / tokens / 10)
    ok = density >= 0.20
    return Finding(
        "info_density", _C, "Information density", ok, "medium",
        f"Density {density:.2f} ({entities} entities, {numbers} numbers across {tokens} tokens). "
        "A high-density article runs about 5 per 100 tokens; a filler post under 2.",
        None if ok else (
            "Add specifics: named tools, companies, standards, dates, measurements, prices.\n"
            "Density is what separates a page that answers a question from one that circles it."
        ),
    )


# ----------------------------------------------------------------- performance

@check
def dom_size(c: Ctx) -> Finding:
    n = len(c.tree.css("*"))
    ok = n <= DOM_MAX
    return Finding(
        "dom_size", _C, "DOM size", ok, "low",
        f"{n} DOM elements." + ("" if ok else f" Over {DOM_MAX} is a known interaction-latency risk."),
        None if ok else (
            f"Reduce the DOM below {DOM_MAX} elements. Large trees slow style recalculation and hurt\n"
            "INP. Look for deeply nested wrappers and long unvirtualised lists."
        ),
    )


@check
def render_blocking(c: Ctx) -> Finding:
    scripts = [s for s in c.tree.css("head script[src]")
               if not s.attributes.get("async") and not s.attributes.get("defer")]
    ok = len(scripts) == 0
    return Finding(
        "render_blocking", _C, "Render-blocking scripts", ok, "medium",
        "No render-blocking scripts in <head>." if ok else
        f"{len(scripts)} script(s) in <head> without async or defer, delaying first paint and LCP.",
        None if ok else (
            "Add defer (or async for independent scripts) to every <head> script:\n\n"
            '  <script src="/app.js" defer></script>'
        ),
    )


@check
def font_display(c: Ctx) -> Finding:
    has_fonts = bool(c.tree.css('link[href*="fonts.googleapis"], link[rel=preconnect][href*="fonts"]')) \
        or "@font-face" in c.snap.html
    if not has_fonts:
        return Finding("font_display", _C, "Web font loading", True, "low", "No web fonts detected.")
    ok = "font-display" in c.snap.html or "display=swap" in c.snap.html
    return Finding(
        "font_display", _C, "Web font loading", ok, "low",
        "Fonts use font-display." if ok else
        "Web fonts load without font-display, so text stays invisible while they download.",
        None if ok else (
            "Add &display=swap to Google Fonts URLs, or font-display: swap to @font-face rules,\n"
            "and preload the font used above the fold."
        ),
    )


# ------------------------------------------------------------- multi-modal (GEO)

@check
def multimodal_content(c: Ctx) -> Finding:
    imgs = len(c.tree.css("img"))
    video = bool(c.tree.css('iframe[src*="youtube"], iframe[src*="vimeo"], iframe[src*="wistia"], video')) \
        or bool({"VideoObject", "Clip", "BroadcastEvent"} & c.schema_types())
    audio = bool(c.tree.css("audio")) or bool({"AudioObject", "PodcastEpisode"} & c.schema_types())
    tables = len(c.tree.css("table"))
    kinds = sum([imgs > 0, video, audio, tables > 0])
    ok = kinds >= 2
    return Finding(
        "multimodal", _C, "Multi-modal content", ok, "medium",
        f"{kinds} content types present ({imgs} images, "
        f"{'video' if video else 'no video'}, {'audio' if audio else 'no audio'}, {tables} tables).",
        None if ok else (
            "Mix formats: add a diagram, a comparison table, or an embedded video with a transcript.\n"
            "Pages carrying multiple media types are selected by answer engines substantially more\n"
            "often than text-only pages."
        ),
    )


@check
def media_transcripts(c: Ctx) -> Finding:
    has_video = bool(c.tree.css('iframe[src*="youtube"], iframe[src*="vimeo"], video')) \
        or "VideoObject" in c.schema_types()
    if not has_video:
        return Finding("media_transcripts", _C, "Media transcripts", True, "low", "No video on this page.")
    ok = bool(c.tree.css("track[kind=captions], track[kind=subtitles]")) \
        or re.search(r"transcript", c.body_text, re.I) is not None
    return Finding(
        "media_transcripts", _C, "Media transcripts", ok, "medium",
        "Captions or a transcript are present." if ok else
        "Video with no captions or transcript. An answer engine cannot watch a video. The transcript "
        "is the only part of it that can ever be cited.",
        None if ok else (
            "Publish the transcript as page text and add a caption track:\n\n"
            '  <track kind="captions" src="captions.vtt" srclang="en" label="English" default>\n\n'
            "Then add VideoObject schema with a transcript property."
        ),
    )
