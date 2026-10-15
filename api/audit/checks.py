"""Every deterministic check, in one list. Adding a check = appending a function."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import cached_property
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from . import fixes
from .fetch import AI_BOTS, SiteSnapshot

CRAWLER, STRUCTURE, CONTENT, TRUST, DELIVERY = "crawler", "structure", "content", "trust", "delivery"

CATEGORY_LABELS = {
    CRAWLER: "AI crawler access",
    STRUCTURE: "Machine-readable structure",
    CONTENT: "Answer-engine content",
    TRUST: "Trust signals",
    DELIVERY: "Delivery",
}

QUESTION_WORDS = ("how ", "what ", "why ", "when ", "where ", "which ", "who ", "best ", "can ", "is ", "do ", "does ")
AUTHORITATIVE_TLDS = (".gov", ".edu", ".org")
AUTHORITATIVE_HOSTS = ("wikipedia.org", "nih.gov", "arxiv.org", "nature.com", "reuters.com", "who.int")


@dataclass
class Finding:
    id: str
    category: str
    title: str
    passed: bool
    severity: str  # critical | high | medium | low | info
    evidence: str
    fix: str | None = None
    weight: float = 1.0

    # Filled from weights.TABLE after the check runs, so check bodies stay
    # focused on detection and every weighting decision lives in one file.
    seo_category: str | None = None
    seo_weight: float = 0.0
    geo_dimension: str | None = None
    geo_weight: float = 0.0
    effort: str = "hours"
    note: str | None = None

    # An advisory is already reflected in a continuously-scored dimension, so it
    # carries no weight of its own. Weighting it would count the same evidence
    # twice. It still needs an audience, because it is real work for someone.
    advisory: bool = False
    audience_override: str | None = None

    @property
    def divergence(self) -> float:
        """Positive = matters more to search. Negative = more to answer engines."""
        return self.seo_weight - self.geo_weight

    @property
    def audience(self) -> str:
        """Who this finding actually costs you."""
        if self.audience_override:
            return self.audience_override
        if self.seo_weight == 0 and self.geo_weight == 0:
            return "neither"
        if self.seo_weight == 0:
            return "ai"
        if self.geo_weight == 0:
            return "search"
        ratio = self.seo_weight / self.geo_weight
        if ratio >= 2:
            return "search"
        if ratio <= 0.5:
            return "ai"
        return "both"


@dataclass
class Ctx:
    """Parsed view of the page. Built once, shared by every check."""

    snap: SiteSnapshot
    _cache: dict = field(default_factory=dict, repr=False)

    @cached_property
    def tree(self) -> HTMLParser:
        return HTMLParser(self.snap.html)

    @cached_property
    def lang(self) -> str:
        """Primary language subtag from <html lang>, e.g. "de" for "de-DE".
        Empty when undeclared, which is treated as English."""
        node = self.tree.css_first("html")
        return ((node.attributes.get("lang") if node else None) or "").split("-")[0].lower()

    @cached_property
    def body_text(self) -> str:
        # Parse a throwaway copy: decompose() mutates the tree in place, and stripping
        # <script> here would destroy the JSON-LD that other checks read off self.tree.
        tree = HTMLParser(self.snap.html)
        for tag in ("script", "style", "noscript", "template", "svg"):
            for node in tree.css(tag):
                node.decompose()
        body = tree.body or tree
        return re.sub(r"\s+", " ", body.text(separator=" ")).strip()

    @cached_property
    def words(self) -> list[str]:
        return self.body_text.split()

    @cached_property
    def headings(self) -> list[tuple[int, str]]:
        out = []
        for node in self.tree.css("h1, h2, h3, h4, h5, h6"):
            text = re.sub(r"\s+", " ", node.text()).strip()
            if text:
                out.append((int(node.tag[1]), text))
        return out

    @cached_property
    def jsonld(self) -> list[dict]:
        blocks = []
        for node in self.tree.css('script[type="application/ld+json"]'):
            try:
                data = json.loads(node.text())
            except (json.JSONDecodeError, ValueError):
                self._cache["jsonld_broken"] = True
                continue
            blocks.extend(data if isinstance(data, list) else [data])
        # @graph containers hold the real entities
        flat = []
        for b in blocks:
            if isinstance(b, dict) and "@graph" in b:
                flat.extend(x for x in b["@graph"] if isinstance(x, dict))
            elif isinstance(b, dict):
                flat.append(b)
        return flat

    def schema_types(self) -> set[str]:
        types = set()
        for block in self.jsonld:
            t = block.get("@type")
            types.update(t if isinstance(t, list) else [t] if t else [])
        return types

    def meta(self, name: str) -> str | None:
        for sel in (f'meta[name="{name}"]', f'meta[property="{name}"]'):
            node = self.tree.css_first(sel)
            if node and node.attributes.get("content"):
                return node.attributes["content"].strip()
        return None

    @cached_property
    def title(self) -> str:
        node = self.tree.css_first("title")
        return node.text().strip() if node else ""

    @cached_property
    def brand(self) -> str:
        og = self.meta("og:site_name")
        if og:
            return og
        for org in self.jsonld:
            if org.get("@type") == "Organization" and org.get("name"):
                return org["name"]
        if self.title:
            # "Page title | Brand" and "Page title - Brand" both put brand last
            parts = re.split(r"\s[|–—-]\s", self.title)
            if len(parts) > 1:
                return parts[-1].strip()
        return self.snap.domain.split(".")[0].title()

    @cached_property
    def links(self) -> list[tuple[str, str]]:
        out = []
        for node in self.tree.css("a[href]"):
            href = node.attributes.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                out.append((urljoin(self.snap.final_url, href), re.sub(r"\s+", " ", node.text()).strip()))
        return out

    @cached_property
    def external_links(self) -> list[tuple[str, str]]:
        return [(u, t) for u, t in self.links if urlparse(u).netloc.removeprefix("www.") != self.snap.domain]

    @cached_property
    def internal_links(self) -> list[tuple[str, str]]:
        return [(u, t) for u, t in self.links if urlparse(u).netloc.removeprefix("www.") == self.snap.domain]

    def sections(self) -> list[int]:
        """Word count of each section between H2/H3 boundaries, which is what a retriever chunks."""
        text = self.body_text
        marks = []
        for level, htext in self.headings:
            if level in (2, 3):
                idx = text.find(htext)
                if idx != -1:
                    marks.append(idx)
        marks = sorted(set(marks))
        if not marks:
            return [len(self.words)] if self.words else []
        bounds = marks + [len(text)]
        return [len(text[bounds[i]:bounds[i + 1]].split()) for i in range(len(bounds) - 1)]


CHECKS: list = []


def check(fn):
    CHECKS.append(fn)
    return fn


# ---------------------------------------------------------------- A. crawler access

@check
def robots_allows_ai_bots(c: Ctx) -> list[Finding]:
    """One finding per bot. "AI bots blocked" is useless; "OAI-SearchBot blocked" is fixable."""
    out = []
    blocked = []
    for probe in c.snap.bot_probes:
        ok = not probe.blocked_by_robots
        if not ok:
            blocked.append(probe.bot)
        out.append(
            Finding(
                id=f"robots_{probe.bot.lower().replace('-', '_')}",
                category=CRAWLER,
                title=f"robots.txt allows {probe.bot}",
                passed=ok,
                severity="critical",
                evidence=(
                    f"{probe.bot} ({AI_BOTS[probe.bot]}) is allowed by robots.txt."
                    if ok
                    else f"robots.txt disallows {probe.bot}. {AI_BOTS[probe.bot]} cannot read this page."
                ),
                fix=None if ok else fixes.robots_allow(c.snap.origin, [probe.bot]),
                weight=2.0,
            )
        )
    if blocked:
        out[0].fix = fixes.robots_allow(c.snap.origin, blocked)
    return out


@check
def edge_not_blocking_bots(c: Ctx) -> Finding:
    """A WAF returning 403 to bot UAs silently undoes a permissive robots.txt."""
    blocked = [p.bot for p in c.snap.bot_probes if p.blocked_by_edge]
    return Finding(
        id="edge_block",
        category=CRAWLER,
        title="No CDN/WAF block on AI crawler user-agents",
        passed=not blocked,
        severity="critical",
        evidence=(
            "All AI crawler user-agents received a successful response."
            if not blocked
            else f"These user-agents were rejected at the edge (403/4xx) even though a browser got through: "
            f"{', '.join(blocked)}. robots.txt permission is irrelevant if the CDN blocks the request."
        ),
        fix=None
        if not blocked
        else (
            "In your CDN/WAF (Cloudflare: Security > Bots, or a WAF custom rule), allowlist these\n"
            "user-agents so they are not challenged or blocked:\n\n"
            + "\n".join(f"  {b}" for b in blocked)
            + "\n\nCloudflare specifically: turn OFF 'Block AI Scrapers and Crawlers' under Security > Bots,\n"
            "or add an exception. Verify with:\n\n"
            + "\n".join(f'  curl -sI -A "{b}/1.0" {c.snap.final_url} | head -1' for b in blocked)
        ),
        weight=2.0,
    )


@check
def content_without_javascript(c: Ctx) -> Finding:
    """AI crawlers do not execute JS. Raw HTML text IS what they see."""
    word_count = len(c.words)
    spa_root = bool(
        c.tree.css_first("#root:empty")
        or c.tree.css_first("#__next:empty")
        or c.tree.css_first("app-root:empty")
        or c.tree.css_first("#app:empty")
    )
    scripts = len(c.tree.css("script[src]"))
    passed = word_count >= 200

    if passed:
        evidence = f"{word_count} words are present in the raw HTML without executing JavaScript."
    elif spa_root or scripts >= 3:
        evidence = (
            f"Only {word_count} words are present in the server-delivered HTML, with an empty app root "
            f"and {scripts} script bundles. This is a client-rendered app: AI crawlers do not execute "
            "JavaScript, so they see a blank page. Nothing else in this report matters until this is fixed."
        )
    else:
        evidence = f"Only {word_count} words in the raw HTML, too thin to be cited as a source."

    return Finding(
        id="no_js_content",
        category=CRAWLER,
        title="Content readable without JavaScript",
        passed=passed,
        severity="critical",
        evidence=evidence,
        fix=None
        if passed
        else (
            "Serve this page's content in the initial HTML response. Options by stack:\n\n"
            "  Next.js   - use Server Components or getServerSideProps/generateStaticParams\n"
            "              (App Router renders server-side by default; check for a stray 'use client'\n"
            "              at the top of the page component)\n"
            "  React SPA - add prerendering (vite-plugin-ssr, react-snap) or move to a framework with SSR\n"
            "  Vue/Nuxt  - ensure ssr: true in nuxt.config\n"
            "  Angular   - enable Angular Universal\n\n"
            "Verify the fix. This must show your real content, not an empty <div>:\n\n"
            f"  curl -s {c.snap.final_url} | grep -o '<body.*' | head -c 2000"
        ),
        weight=3.0,
    )


# ------------------------------------------------------------- B. machine-readable

@check
def has_llms_txt(c: Ctx) -> Finding:
    txt = c.snap.llms_txt
    ok = bool(txt and txt.lstrip().startswith("#") and len(txt) > 50)
    pages = [(t, u) for u, t in c.internal_links if t and len(t) > 3][:10]
    return Finding(
        id="llms_txt",
        category=STRUCTURE,
        title="/llms.txt present",
        passed=ok,
        severity="medium",
        evidence=(
            "/llms.txt is present and well-formed."
            if ok
            else "No /llms.txt found. It is an emerging convention, not yet universally consumed, but it is "
            "cheap: a markdown index telling AI clients which pages matter and what they cover."
        ),
        fix=None
        if ok
        else f"Create /llms.txt at your site root:\n\n{fixes.llms_txt(c.brand, c.snap.origin, c.meta('description') or '', [(t, u) for t, u in pages])}",
    )


@check
def content_signal_policy(c: Ctx) -> Finding:
    """Cloudflare's Content-Signal syntax inside robots.txt.

    robots.txt says who may *fetch*. Content-Signal says what they may then
    *do* — search, ai-input (grounding an answer), ai-train. Declaring
    ai-input=yes is the one machine-readable way to say "quote me", and it is
    the opposite lever from the blanket AI blocks most sites reach for.
    """
    robots = c.snap.robots_txt or ""
    directives = [
        ln.split(":", 1)[1].strip()
        for ln in robots.splitlines()
        if ln.split("#", 1)[0].strip().lower().startswith("content-signal:")
    ]
    joined = ",".join(directives).lower()
    declared = bool(directives)
    # yes/no per key; absent means undeclared, which is not the same as "no".
    opted_out = "ai-input=no" in joined.replace(" ", "")

    return Finding(
        id="content_signal",
        category=CRAWLER,
        title="Content-Signal declares AI usage",
        passed=declared and not opted_out,
        severity="low",
        evidence=(
            f"robots.txt declares Content-Signal: {'; '.join(directives)}"
            if declared and not opted_out
            else f"robots.txt sets ai-input=no, which asks answer engines not to ground answers in "
            f"this page even when they are allowed to fetch it: {'; '.join(directives)}"
            if opted_out
            else "No Content-Signal directive in robots.txt. Fetch permission is declared, intent is not, "
            "so an engine weighing whether it may quote you has nothing to read."
        ),
        fix=None
        if declared and not opted_out
        else "Add to robots.txt, above your User-agent groups:\n\n"
        "  Content-Signal: search=yes, ai-input=yes, ai-train=no\n\n"
        "That permits indexing and answer-grounding while withholding training.",
    )


@check
def markdown_alternative(c: Ctx) -> Finding:
    """A markdown twin of the page, advertised for machine readers.

    Answer engines parse markdown far more reliably than a JS-heavy DOM. Sites
    expose it either as <link rel="alternate" type="text/markdown"> or by
    serving the same path with a .md suffix.
    """
    alts = [
        urljoin(c.snap.final_url, n.attributes.get("href", ""))
        for n in c.tree.css('link[rel="alternate"]')
        if "markdown" in (n.attributes.get("type") or "").lower()
    ]
    ok = bool(alts)
    return Finding(
        id="markdown_alt",
        category=STRUCTURE,
        title="Markdown alternative advertised",
        passed=ok,
        severity="low",
        evidence=(
            f"A markdown alternative is advertised at {alts[0]}."
            if ok
            else "No markdown alternative advertised. Answer engines parse markdown far more "
            "reliably than rendered HTML, and there is no cost to offering both."
        ),
        fix=None
        if ok
        else "Serve a plain-markdown twin of each key page and advertise it in <head>:\n\n"
        '  <link rel="alternate" type="text/markdown" href="/this-page.md">',
    )


# --------------------------------------------------------------- content quality
#
# Heuristics aligned to Google's Quality Rater Guidelines (Sept 2025) §4.6 on
# filler and §4.6.5 on scaled content abuse. Ported from AgriciDaniel/claude-seo
# (MIT); the LLM-phrasing catalogue there credits Wikipedia's AI Cleanup project
# (CC BY-SA 4.0).
#
# These are advisory signals, never a verdict. A capable writer clears every
# threshold and a capable model can too, so a hit means "worth a human look",
# not "this was generated".

FILLER_PHRASES = (
    "it's important to note that", "in this article, we'll explore", "in today's fast-paced world",
    "in today's digital age", "in today's competitive landscape", "needless to say",
    "at the end of the day", "when it comes to", "in the realm of", "in the world of",
    "the bottom line is", "without further ado", "first and foremost", "last but not least",
    "it goes without saying", "as we all know", "the truth is that",
    "the fact of the matter is", "more often than not", "let's dive in", "let's dive into",
    "let's take a closer look",
)

AI_PATTERNS = (
    "delve into", "delve deeper into", "in the ever-evolving", "ever-evolving landscape",
    "ever-changing landscape", "navigate the complexities", "tapestry of", "rich tapestry",
    "embark on a journey", "a testament to", "a beacon of", "the cornerstone of",
    "at its core", "in essence,", "in conclusion,", "it's worth noting that",
    "by leveraging", "leverage the power of", "harness the power of", "unlock the potential",
    "unlock the full potential", "a world of possibilities", "elevate your",
    "revolutionize the way", "game-changer", "game-changing",
)

_ENTITY_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_NUMBER_RE = re.compile(r"\b\d[\d,.]*\b")


def _phrase_hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    low = text.lower()
    return [p for p in phrases if p in low]


@check
def filler_content(c: Ctx) -> Finding:
    """Padding phrases that carry no information."""
    hits = _phrase_hits(c.body_text, FILLER_PHRASES)
    # Per 1000 words, so a long page is not punished for length alone.
    scale = max(1.0, len(c.words) / 1000.0)
    rate = len(hits) / scale
    ok = rate < 2.0
    return Finding(
        id="filler_content",
        category=CONTENT,
        title="Free of filler phrasing",
        passed=ok,
        severity="medium",
        evidence=(
            "No significant filler phrasing."
            if ok
            else f"{len(hits)} filler phrase(s) per 1000 words, including "
            f"{', '.join(repr(h) for h in hits[:3])}. Padding pushes the answer further down the "
            "page, and an engine extracting a quote has to wade through it."
        ),
        fix=None
        if ok
        else "Cut the padding and lead with the claim. Every sentence that survives should carry "
        "a fact, a number or a decision.",
    )


@check
def ai_phrasing(c: Ctx) -> Finding:
    """LLM-typical phrasing, which correlates with unedited generated drafts."""
    hits = _phrase_hits(c.body_text, AI_PATTERNS)
    scale = max(1.0, len(c.words) / 1000.0)
    rate = len(hits) / scale
    ok = rate < 3.0
    return Finding(
        id="ai_phrasing",
        category=CONTENT,
        title="Free of unedited AI phrasing",
        passed=ok,
        severity="medium",
        evidence=(
            "No concentration of LLM-typical phrasing."
            if ok
            else f"{len(hits)} LLM-typical phrase(s) per 1000 words, including "
            f"{', '.join(repr(h) for h in hits[:3])}. This is a signal an editor never passed over "
            "the draft, which is what Google's scaled-content-abuse guidance targets."
        ),
        fix=None
        if ok
        else "Edit the draft in your own voice. The phrases above are the ones models reach for "
        "by default, so replacing them is usually enough.",
    )


@check
def information_density(c: Ctx) -> Finding:
    """Named things and numbers per 100 words.

    A page an answer engine can quote is specific: it names products, people,
    places and figures. Generic prose has nothing worth lifting.
    """
    n = len(c.words)
    if n < 50:
        return Finding(
            id="information_density",
            category=CONTENT,
            title="Specific enough to quote",
            passed=False,
            severity="high",
            evidence=f"Only {n} words of body copy. There is not enough here to extract an answer from.",
            fix="Write at least a few hundred words that answer a real question.",
        )
    facts = len(_ENTITY_RE.findall(c.body_text)) + len(_NUMBER_RE.findall(c.body_text))
    per_100 = facts * 100.0 / n
    # Calibrated against real pages: generic marketing prose lands near 4,
    # factual writing at 30+. Live samples: stripe.com 51, a Wikipedia article
    # 31. The bar sits above filler with room for thinner but genuine writing.
    ok = per_100 >= 8.0
    return Finding(
        id="information_density",
        category=CONTENT,
        title="Specific enough to quote",
        passed=ok,
        severity="medium",
        evidence=(
            f"{per_100:.1f} named things or figures per 100 words."
            if ok
            else f"Only {per_100:.1f} named things or figures per 100 words. Answer engines quote "
            "specifics: names, places, versions, prices, dates. Generic prose gives them nothing to lift."
        ),
        fix=None
        if ok
        else "Add concrete detail: real numbers, product names, dates, place names. Replace "
        "'significantly faster' with the actual figure.",
    )


# ------------------------------------------------------------------- agent UX
#
# An answer engine that wants to *act* on your site, not just read it, needs
# controls it can identify. A div with an onclick handler is invisible to it.

_ONCLICK_DIV_RE = re.compile(r"<(?:div|span)\b[^>]*\bonclick\s*=", re.I)
_LANDMARK_RE = re.compile(r"<(?:nav|main|article|section|aside|header|footer)\b", re.I)


@check
def semantic_landmarks(c: Ctx) -> Finding:
    """<main>, <nav>, <article> and friends, which tell an agent where it is."""
    found = sorted({m.lower() for m in re.findall(r"<(nav|main|article|header|footer|aside)\b", c.snap.html, re.I)})
    # <main> is the load-bearing one: it is what separates content from chrome.
    # Counting the rest would fail a clean page that simply has less furniture.
    ok = "main" in found
    return Finding(
        id="semantic_landmarks",
        category=STRUCTURE,
        title="Semantic landmarks present",
        passed=ok,
        severity="medium",
        evidence=(
            f"Landmarks present: {', '.join('<' + f + '>' for f in found)}."
            if ok
            else f"No <main> element. Landmarks found: "
            f"{', '.join('<' + f + '>' for f in found) or 'none'}. Without <main> an agent cannot "
            "tell your content from your chrome, and lifts the navigation along with the answer."
        ),
        fix=None
        if ok
        else "Wrap the page body in <main>, the menu in <nav> and each self-contained piece in "
        "<article>. This is a change to the wrapper tags only.",
    )


@check
def real_controls(c: Ctx) -> Finding:
    """Real <button>/<a href> rather than click-handler divs."""
    fake = len(_ONCLICK_DIV_RE.findall(c.snap.html))
    real = len(c.tree.css("button")) + len([a for a in c.tree.css("a") if a.attributes.get("href")])
    ok = fake == 0 or (real and fake / max(1, real) < 0.2)
    return Finding(
        id="real_controls",
        category=STRUCTURE,
        title="Controls are real buttons and links",
        passed=ok,
        severity="low",
        evidence=(
            f"{real} real control(s) and {fake} click-handler div(s)."
            if ok
            else f"{fake} clickable div/span(s) against {real} real control(s). An agent reading "
            "the page sees no control at all where a div handles the click."
        ),
        fix=None
        if ok
        else "Replace <div onclick=...> with <button> for actions and <a href> for navigation. "
        "Both are keyboard-reachable and screen-reader-visible for free.",
    )


@check
def labelled_inputs(c: Ctx) -> Finding:
    """Every input reachable by name."""
    inputs = [n for n in c.tree.css("input") if (n.attributes.get("type") or "text").lower()
              not in {"hidden", "submit", "button", "image", "reset"}]
    if not inputs:
        return Finding(
            id="labelled_inputs", category=STRUCTURE, title="Form inputs are labelled",
            passed=True, severity="low", evidence="No form inputs on the page.",
        )
    label_targets = {n.attributes.get("for") for n in c.tree.css("label") if n.attributes.get("for")}
    # An input nested inside its <label> is implicitly associated and needs no
    # `for`. Missing this reports a correctly built form as unlabelled, which is
    # worse than silence: it sends someone to "fix" working markup.
    def wrapped_in_label(node) -> bool:
        parent = node.parent
        while parent is not None:
            if parent.tag == "label":
                return True
            parent = parent.parent
        return False

    unlabelled = [
        n for n in inputs
        if not n.attributes.get("aria-label")
        and not n.attributes.get("aria-labelledby")
        and n.attributes.get("id") not in label_targets
        and not wrapped_in_label(n)
    ]
    ok = not unlabelled
    return Finding(
        id="labelled_inputs",
        category=STRUCTURE,
        title="Form inputs are labelled",
        passed=ok,
        severity="low",
        evidence=(
            f"All {len(inputs)} input(s) carry a label."
            if ok
            else f"{len(unlabelled)} of {len(inputs)} input(s) have no <label for>, aria-label or "
            "aria-labelledby. An agent filling the form cannot tell what the field wants."
        ),
        fix=None
        if ok
        else 'Give each input a <label for="its-id"> or an aria-label. This is also the single '
        "highest-value accessibility fix on most forms.",
    )


@check
def has_sitemap(c: Ctx) -> Finding:
    ok = bool(c.snap.sitemap_urls)
    referenced = bool(c.snap.robots_sitemap_refs)
    return Finding(
        id="sitemap",
        category=STRUCTURE,
        title="Sitemap present and referenced in robots.txt",
        passed=ok and referenced,
        severity="medium",
        evidence=(
            f"Sitemap found at {c.snap.sitemap_urls[0]} and referenced in robots.txt."
            if ok and referenced
            else f"Sitemap reachable at {c.snap.sitemap_urls[0]} but not referenced in robots.txt."
            if ok
            else "No reachable sitemap.xml found."
        ),
        fix=None if (ok and referenced) else f"Add to robots.txt:\n\n  Sitemap: {c.snap.origin}/sitemap.xml",
    )


@check
def has_valid_jsonld(c: Ctx) -> Finding:
    blocks = c.jsonld  # force the parse before reading the broken-JSON flag it sets
    broken = c._cache.get("jsonld_broken", False)
    ok = bool(blocks) and not broken
    return Finding(
        id="jsonld_present",
        category=STRUCTURE,
        title="Valid JSON-LD structured data",
        passed=ok,
        severity="high",
        evidence=(
            f"{len(blocks)} JSON-LD block(s) parsed: {', '.join(sorted(c.schema_types())) or 'untyped'}."
            if ok
            else "A JSON-LD block is present but does not parse as valid JSON."
            if broken
            else "No JSON-LD structured data found. Schema is how you state facts about yourself in a form "
            "that needs no inference."
        ),
        fix=None if ok else fixes.organization_jsonld(c.brand, c.snap.origin, c.meta("description") or ""),
        weight=1.5,
    )


@check
def has_entity_schema(c: Ctx) -> Finding:
    """sameAs links are what tie a site to a known entity in a knowledge graph."""
    entity = next(
        (b for b in c.jsonld if b.get("@type") in ("Organization", "Person") or
         (isinstance(b.get("@type"), list) and {"Organization", "Person"} & set(b["@type"]))),
        None,
    )
    same_as = entity.get("sameAs") if entity else None
    ok = bool(entity and same_as)
    return Finding(
        id="entity_schema",
        category=STRUCTURE,
        title="Organization/Person schema with sameAs entity links",
        passed=ok,
        severity="high",
        evidence=(
            f"Entity schema present with {len(same_as if isinstance(same_as, list) else [same_as])} sameAs link(s)."
            if ok
            else "Organization schema present but has no sameAs links, so it is not tied to any known entity."
            if entity
            else "No Organization or Person schema. AI engines cannot confirm who publishes this site."
        ),
        fix=None if ok else fixes.organization_jsonld(c.brand, c.snap.origin, c.meta("description") or ""),
        weight=1.5,
    )


@check
def has_page_type_schema(c: Ctx) -> Finding:
    useful = {"Article", "BlogPosting", "NewsArticle", "Product", "FAQPage", "HowTo", "SoftwareApplication", "Recipe", "Course", "Event"}
    found = useful & c.schema_types()
    questions = [h for lvl, h in c.headings if h.rstrip().endswith("?")]
    return Finding(
        id="page_type_schema",
        category=STRUCTURE,
        title="Page-level schema (Article / Product / FAQPage)",
        passed=bool(found),
        severity="medium",
        evidence=(
            f"Page-level schema present: {', '.join(sorted(found))}."
            if found
            else "No page-level schema. Only site-wide schema was found, which says nothing about this page."
        ),
        fix=None
        if found
        else (
            fixes.qa_jsonld(questions)
            if questions
            else fixes.article_jsonld(c.title or "Page title", c.snap.final_url, c.brand)
        ),
    )


@check
def schema_required_fields(c: Ctx) -> Finding:
    """A schema block missing required fields is ignored, which is worse than absent, because it looks done."""
    required = {
        "Article": ["headline", "author", "datePublished"],
        "BlogPosting": ["headline", "author", "datePublished"],
        "NewsArticle": ["headline", "author", "datePublished"],
        "Product": ["name"],
        "Organization": ["name", "url"],
        "FAQPage": ["mainEntity"],
        "HowTo": ["name", "step"],
    }
    problems = []
    for block in c.jsonld:
        types = block.get("@type")
        for t in types if isinstance(types, list) else [types]:
            for f in required.get(t, []):
                if not block.get(f):
                    problems.append(f"{t} is missing required field '{f}'")
    ok = not problems
    return Finding(
        id="schema_fields",
        category=STRUCTURE,
        title="Schema blocks have their required fields",
        passed=ok,
        severity="medium",
        evidence="All detected schema blocks have their required fields." if ok else "; ".join(problems[:5]),
        fix=None if ok else "Add the missing fields listed above. Validate at https://validator.schema.org/",
    )


@check
def has_canonical(c: Ctx) -> Finding:
    node = c.tree.css_first('link[rel="canonical"]')
    href = node.attributes.get("href", "").strip() if node else ""
    resolved = urljoin(c.snap.final_url, href) if href else ""
    ok = bool(resolved)
    consistent = resolved.rstrip("/") == c.snap.final_url.rstrip("/")
    return Finding(
        id="canonical",
        category=STRUCTURE,
        title="Canonical URL declared",
        passed=ok,
        severity="low",
        evidence=(
            f"Canonical points to {resolved}." + ("" if consistent else " Note: this differs from the fetched URL.")
            if ok
            else "No canonical link. Duplicate URLs can split citation signals across variants."
        ),
        fix=None if ok else f'<link rel="canonical" href="{c.snap.final_url}" />',
    )


@check
def has_meta_description(c: Ctx) -> Finding:
    desc = c.meta("description") or ""
    og_title = c.meta("og:title")
    ok = len(desc) >= 50
    return Finding(
        id="meta_description",
        category=STRUCTURE,
        title="Meta description and Open Graph tags",
        passed=ok and bool(og_title),
        severity="low",
        evidence=(
            f"Meta description present ({len(desc)} chars) with Open Graph tags."
            if ok and og_title
            else f"Meta description is {len(desc)} chars (want 50+); og:title is {'present' if og_title else 'missing'}."
        ),
        fix=None
        if (ok and og_title)
        else (
            f'<meta name="description" content="A direct one-sentence summary of what this page answers." />\n'
            f'<meta property="og:title" content="{c.title or "Page title"}" />\n'
            f'<meta property="og:description" content="Same summary as above." />\n'
            f'<meta property="og:site_name" content="{c.brand}" />'
        ),
    )


# ------------------------------------------------------------------- C. content

@check
def single_h1(c: Ctx) -> Finding:
    h1s = [h for lvl, h in c.headings if lvl == 1]
    ok = len(h1s) == 1
    return Finding(
        id="single_h1",
        category=CONTENT,
        title="Exactly one H1",
        passed=ok,
        severity="low",
        evidence=f'One H1: "{h1s[0][:80]}".' if ok else f"Found {len(h1s)} H1 elements.",
        fix=None if ok else "Use exactly one H1 stating the page's subject; demote the rest to H2.",
    )


@check
def heading_hierarchy(c: Ctx) -> Finding:
    levels = [lvl for lvl, _ in c.headings]
    skips = [(levels[i], levels[i + 1]) for i in range(len(levels) - 1) if levels[i + 1] - levels[i] > 1]
    ok = not skips and len(levels) >= 2
    return Finding(
        id="heading_hierarchy",
        category=CONTENT,
        title="Logical heading hierarchy",
        passed=ok,
        severity="medium",
        evidence=(
            f"{len(levels)} headings nest without skipping levels."
            if ok
            else f"Heading levels skip: {', '.join(f'H{a}->H{b}' for a, b in skips[:3])}."
            if skips
            else f"Only {len(levels)} heading(s), too few to give the page a retrievable structure."
        ),
        fix=None if ok else "Do not skip levels (H2 then H4). Headings are the section boundaries retrievers chunk on.",
    )


@check
def question_headings(c: Ctx) -> Finding:
    """Headings that match how people actually ask get matched to those queries."""
    qs = [h for _, h in c.headings if h.rstrip().endswith("?") or h.lower().startswith(QUESTION_WORDS)]
    ok = len(qs) >= 2
    return Finding(
        id="question_headings",
        category=CONTENT,
        title="Question-shaped headings",
        passed=ok,
        severity="medium",
        evidence=(
            f'{len(qs)} question-shaped heading(s), e.g. "{qs[0][:70]}".'
            if ok
            else f"{'No headings are' if not qs else 'Only ' + str(len(qs)) + ' heading is' if len(qs) == 1 else 'Only ' + str(len(qs)) + ' headings are'} "
            "phrased as a question or query. Headings like "
            '"Features" do not match what anyone asks an AI assistant.'
        ),
        fix=None
        if ok
        else (
            "Rewrite section headings to mirror real queries, then answer immediately beneath:\n\n"
            "  Features            ->  What can {b} do?\n"
            "  Pricing             ->  How much does {b} cost?\n"
            "  Getting started     ->  How do I set up {b}?\n"
            "  Comparison          ->  {b} vs alternatives: which should I use?"
        ).format(b=c.brand),
    )


@check
def answer_first(c: Ctx) -> Finding:
    """A self-contained answer near the top is what gets lifted into a generated response."""
    text = c.body_text
    h2s = [h for lvl, h in c.headings if lvl == 2]
    scored = 0
    for h in h2s:
        idx = text.find(h)
        if idx == -1:
            continue
        after = text[idx + len(h): idx + len(h) + 400].strip()
        sentences = re.split(r"(?<=[.!?])\s+", after)
        first = sentences[0] if sentences else ""
        # A good opener is a real sentence, not a fragment or a lead-in to a list.
        if 40 <= len(first) <= 300 and not first.endswith(":"):
            scored += 1
    ratio = scored / len(h2s) if h2s else 0
    ok = ratio >= 0.6 and len(h2s) >= 2
    return Finding(
        id="answer_first",
        category=CONTENT,
        title="Sections open with a direct answer",
        passed=ok,
        severity="high",
        evidence=(
            f"{scored} of {len(h2s)} sections open with a self-contained answer sentence."
            if h2s
            else "No H2 sections to evaluate."
        ),
        fix=None
        if ok
        else (
            "Put the answer in the first sentence after each heading, before context or narrative.\n"
            "Generated answers lift self-contained sentences; a sentence that depends on the\n"
            "paragraph above it cannot be lifted.\n\n"
            "  Weak:   ## How much does it cost?\n"
            "          We offer a range of plans designed to suit teams of every size...\n\n"
            "  Strong: ## How much does it cost?\n"
            f"          {c.brand} costs $29/month for the Starter plan and $99/month for Pro,\n"
            "          with a free tier limited to 100 scans per month."
        ),
        weight=2.0,
    )


@check
def chunkability(c: Ctx) -> Finding:
    secs = c.sections()
    if not secs:
        return Finding("chunkability", CONTENT, "Sections are a retrievable length", False, "medium",
                       "No content sections found.", "Break the page into H2 sections of 150-800 words.")
    walls = [s for s in secs if s > 800]
    fragments = [s for s in secs if s < 100]
    avg = sum(secs) // len(secs)
    ok = not walls and len(fragments) <= len(secs) // 2
    return Finding(
        id="chunkability",
        category=CONTENT,
        title="Sections are a retrievable length",
        passed=ok,
        severity="medium",
        evidence=(
            f"{len(secs)} sections averaging {avg} words, a good chunk size."
            if ok
            else f"{len(secs)} sections averaging {avg} words: {len(walls)} over 800 words, "
            f"{len(fragments)} under 100. Retrievers split on headings, so a wall of text returns "
            "diluted and a fragment returns without context."
        ),
        fix=None if ok else "Target 150-800 words between H2/H3 headings. Split long sections; merge stubs.",
    )


@check
def extractable_formats(c: Ctx) -> Finding:
    """Lists and tables are lifted into answers far more often than prose."""
    lists = len(c.tree.css("ul li, ol li"))
    tables = len(c.tree.css("table"))
    ok = lists >= 5 or tables >= 1
    return Finding(
        id="extractable_formats",
        category=CONTENT,
        title="Lists and tables present",
        passed=ok,
        severity="medium",
        evidence=(
            f"{lists} list items and {tables} table(s), directly extractable."
            if ok
            else f"Only {lists} list items and {tables} tables. Comparisons and steps buried in prose "
            "are rarely quoted."
        ),
        fix=None
        if ok
        else (
            "Convert comparisons to a <table> and sequences to <ol>. A pricing or feature comparison\n"
            "as a real table gets quoted; the same information in a paragraph does not."
        ),
    )


@check
def has_statistics(c: Ctx) -> Finding:
    """Specific numbers are what a generated answer can cite you for."""
    stats = re.findall(r"\b\d[\d,.]*\s*(?:%|percent|x\b|million|billion|users|customers|ms\b|seconds)", c.body_text, re.I)
    ok = len(stats) >= 3
    return Finding(
        id="statistics",
        category=CONTENT,
        title="Concrete statistics and figures",
        passed=ok,
        severity="medium",
        evidence=(
            f"{len(stats)} concrete figures found, e.g. {', '.join(stats[:3])}."
            if ok
            else f"{'No' if not stats else 'Only ' + str(len(stats))} concrete "
            f"{'figures' if len(stats) != 1 else 'figure'} found. Pages that carry specific numbers get cited as the "
            "source of those numbers; pages of adjectives do not."
        ),
        fix=None
        if ok
        else (
            "Replace vague claims with figures you can stand behind:\n\n"
            '  "significantly faster"  ->  "3.2x faster (180ms vs 580ms median)"\n'
            '  "trusted by many"       ->  "used by 4,200 teams"\n'
            '  "high accuracy"         ->  "94.1% accuracy on the XYZ benchmark"'
        ),
        weight=1.5,
    )


@check
def outbound_citations(c: Ctx) -> Finding:
    authoritative = [
        (u, t)
        for u, t in c.external_links
        if any(h in u for h in AUTHORITATIVE_HOSTS) or urlparse(u).netloc.endswith(AUTHORITATIVE_TLDS)
    ]
    ok = len(authoritative) >= 2
    return Finding(
        id="outbound_citations",
        category=CONTENT,
        title="Citations to authoritative sources",
        passed=ok,
        severity="low",
        evidence=(
            f"{len(authoritative)} link(s) to authoritative domains."
            if ok
            else f"{len(c.external_links)} external links, {len(authoritative)} to authoritative sources. "
            "Citing sources is a signal of the same kind of rigor the engines reward."
        ),
        fix=None if ok else "Link claims to primary sources: research papers, standards bodies, official docs.",
    )


# --------------------------------------------------------------------- D. trust

@check
def named_author(c: Ctx) -> Finding:
    schema_author = next(
        (b["author"] for b in c.jsonld if b.get("author")),
        None,
    )
    author_name = None
    if isinstance(schema_author, dict):
        author_name = schema_author.get("name")
    elif isinstance(schema_author, str):
        author_name = schema_author
    elif isinstance(schema_author, list) and schema_author:
        first = schema_author[0]
        author_name = first.get("name") if isinstance(first, dict) else first

    byline = c.tree.css_first('[rel="author"], .author, .byline, [itemprop="author"]')
    ok = bool(author_name or byline)
    return Finding(
        id="named_author",
        category=TRUST,
        title="Named author",
        passed=ok,
        severity="medium",
        evidence=(
            f'Author identified: "{author_name or byline.text().strip()[:60]}".'
            if ok
            else "No named author in schema or markup. Anonymous content is weighted down for anything "
            "where expertise matters."
        ),
        fix=None
        if ok
        else (
            'Add a visible byline linking to an author page, and declare it in schema:\n\n'
            '  <a rel="author" href="/about/jane-doe">Jane Doe</a>\n\n'
            + fixes.article_jsonld(c.title or "Page title", c.snap.final_url, c.brand)
        ),
    )


@check
def visible_dates(c: Ctx) -> Finding:
    schema_dates = [b.get(k) for b in c.jsonld for k in ("datePublished", "dateModified") if b.get(k)]
    time_nodes = c.tree.css("time[datetime]")
    text_dates = re.findall(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|\b\d{4}-\d{2}-\d{2}\b",
        c.body_text,
    )
    ok = bool(schema_dates or time_nodes or text_dates)
    return Finding(
        id="visible_dates",
        category=TRUST,
        title="Publish / updated dates",
        passed=ok,
        severity="medium",
        evidence=(
            f"Dates found ({len(schema_dates)} in schema, {len(time_nodes)} <time> elements, "
            f"{len(text_dates)} in text)."
            if ok
            else "No publish or last-updated date. Engines prefer content they can confirm is current, and "
            "undated content is treated as unknown age."
        ),
        fix=None
        if ok
        else (
            '<time datetime="2026-09-21">Last updated: September 21, 2026</time>\n\n'
            "and in your Article schema:\n"
            '  "datePublished": "2026-01-15",\n  "dateModified": "2026-09-21"'
        ),
    )


@check
def about_and_contact(c: Ctx) -> Finding:
    hrefs = " ".join(u.lower() for u, _ in c.internal_links)
    has_about = any(k in hrefs for k in ("/about", "/team", "/company", "/who-we-are"))
    has_contact = any(k in hrefs for k in ("/contact", "/support", "/help"))
    ok = has_about and has_contact
    return Finding(
        id="about_contact",
        category=TRUST,
        title="About and contact pages reachable",
        passed=ok,
        severity="low",
        evidence=(
            "About and contact pages are linked from this page."
            if ok
            else f"Missing link to {'an about page' if not has_about else ''}"
            f"{' and ' if not has_about and not has_contact else ''}"
            f"{'a contact page' if not has_contact else ''}."
        ),
        fix=None if ok else "Link /about and /contact from the site footer. Both are baseline publisher-legitimacy signals.",
    )


# ------------------------------------------------------------------ E. delivery

@check
def freshness(c: Ctx) -> Finding:
    lm = c.snap.headers.get("last-modified")
    age_days = None
    if lm:
        try:
            age_days = (datetime.now(timezone.utc) - parsedate_to_datetime(lm)).days
        except (TypeError, ValueError):
            age_days = None
    ok = age_days is None or age_days < 365
    return Finding(
        id="freshness",
        category=DELIVERY,
        title="Content is recent",
        passed=ok,
        severity="low",
        evidence=(
            f"Last-Modified is {age_days} days old." if age_days is not None else "No Last-Modified header (not required)."
        ),
        fix=None if ok else "Refresh and re-date stale pages; engines discount content they can tell is old.",
    )


@check
def delivery_speed(c: Ctx) -> Finding:
    slow = c.snap.ttfb_ms > 2000
    heavy = c.snap.bytes > 2_000_000
    ok = not (slow or heavy)
    return Finding(
        id="delivery_speed",
        category=DELIVERY,
        title="Fast enough for crawler timeouts",
        passed=ok,
        severity="low",
        evidence=(
            f"Responded in {c.snap.ttfb_ms:.0f}ms, {c.snap.bytes / 1024:.0f}KB."
            if ok
            else f"Responded in {c.snap.ttfb_ms:.0f}ms, {c.snap.bytes / 1024:.0f}KB. Crawlers abandon slow "
            "responses far sooner than browsers do."
        ),
        fix=None if ok else "Cache HTML at the edge and compress the response. Aim under 800ms TTFB.",
    )


def apply_weights(findings: list[Finding]) -> list[Finding]:
    """Stamp each finding with its SEO/GEO weighting. Idempotent."""
    from .weights import lookup

    for f in findings:
        if f.advisory:
            continue  # carries its own zero weights and its own effort
        w = lookup(f.id)
        f.seo_category, f.seo_weight = w.seo_category, w.seo_weight
        f.geo_dimension, f.geo_weight = w.geo_dimension, w.geo_weight
        f.effort, f.note = w.effort, w.note
    return findings


def run_all(snap: SiteSnapshot) -> list[Finding]:
    ctx = Ctx(snap)
    out: list[Finding] = []
    for fn in CHECKS:
        result = fn(ctx)
        out.extend(result if isinstance(result, list) else [result])
    return apply_weights(out)
