"""The 47-method citability engine, ported from geo-optimizer.

Scores how quotable a page is to an answer engine. Every threshold, regex and
weight is taken from the source rather than re-derived, because the numbers are
the value: they come from measured citation studies, not intuition.

    raw          = sum(method.score)
    max_possible = sum(method.max_score)   # 210 with the current weights
    score        = round(100 * raw / max_possible)

The `impact` labels in the source ("+41%") are display-only and deliberately do
NOT enter the arithmetic; the weight is max_score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

# ------------------------------------------------------------------- patterns

AUTHORITATIVE_TLDS = (".edu", ".gov", ".org")
AUTHORITATIVE_DOMAINS = {
    "wikipedia.org", "pubmed.ncbi.nlm.nih.gov", "scholar.google.com", "nature.com",
    "sciencedirect.com", "jstor.org", "arxiv.org", "ncbi.nlm.nih.gov", "who.int",
    "cdc.gov", "europa.eu", "springer.com", "ieee.org",
}

QUOTE_ATTRIBUTION_RE = re.compile(r'["“][^"”]{10,300}["”]\s*(?:[-—–])\s*\w+')
STAT_RE = re.compile(
    # German, French and Italian put a (non-breaking) space before % and use a
    # decimal comma: "94 %", "3,5 %". Matching only "94%" failed every
    # translated page for following its own language's typography.
    r"\b\d+(?:[.,]\d+)?[   ]?%|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"
    r"|\$\d+(?:[.,]\d+)*(?:\s*(?:M|B|K|million|billion|thousand))?\b"
    r"|\b\d+\s*(?:million|billion|trillion|thousand)\b|\b\d+(?:\.\d+)?\s*(?:x|X)\b",
    re.I,
)
CONNECTIVES_RE = re.compile(
    r"\b(?:therefore|consequently|furthermore|moreover|however|nevertheless"
    r"|in addition|as a result|for example|for instance|in conclusion"
    r"|specifically|in particular|in contrast)\b", re.I,
)
AUTHORITY_RE = re.compile(
    r"\b(?:according to|research (?:shows?|indicates?|demonstrates?)"
    r"|studies? (?:show|indicate|demonstrate|confirm)"
    r"|evidence (?:shows?|suggests?|indicates?)|experts? (?:agree|recommend|suggest)"
    r"|data (?:shows?|indicates?|reveals?)|proven|demonstrated|established)\b", re.I,
)
HEDGE_RE = re.compile(r"\b(?:might be|could possibly|maybe|perhaps|somewhat|kind of|sort of|seems like)\b", re.I)
_UPPER_STOP = r"AM|AN|AS|AT|BE|BY|DO|GO|HE|IF|IN|IS|IT|ME|MY|NO|OF|ON|OR|SO|TO|UP|US|WE"
TECH_RE = re.compile(
    r"\b(?!(?:" + _UPPER_STOP + r")\b)[A-Z]{2,6}\b|\bv\d+\.\d+(?:\.\d+)?\b"
    r"|\bRFC\s*\d+\b|\bISO\s*\d+\b|\b(?:IEEE|IETF|W3C|ECMA)\b|`[^`]+`"
)
FACT_RE = re.compile(
    r"\b\d+(?:\.\d+)?%|\$\d+|\b\d{2,}\b"
    r"|\b(?:is|are|was|were|has|have|can|will|must|should)\b", re.I,
)
GENERIC_ALT_RE = re.compile(
    r"^(?:image|photo|picture|img|foto|immagine|screenshot|banner|icon|logo"
    r"|img\d+|image\d+|photo\d+|dsc\d+|pic\d+|untitled)$", re.I,
)
CITABLE_NUMERIC_RE = re.compile(
    # Same locale fix as STAT_RE: "94 %" and "3,5 %", plus euro amounts written
    # the European way with the symbol after the number, "5.000 €".
    r"\b\d+(?:[.,]\d+)?[ \u00a0\u202f]?%|\$\d+(?:[.,]\d+)*|€\d+(?:[.,]\d+)*"
    r"|\b\d+(?:[.,]\d+)*[ \u00a0\u202f]?€|\b\d{4}\b"
    r"|\b\d+(?:\.\d+)?\s*(?:million|billion|thousand)\b|\b\d+(?:\.\d+)?\s*(?:x|times)\b", re.I,
)
PROPER_NAME_RE = re.compile(
    r"(?<!\.\s)(?<!^)\b(?!(?:The|This|That|These|Those|What|When|Where|Which|Who|How|"
    r"And|But|For|Nor|Yet|Some|Most|Both|Each|Such|Not|Can|May|Will|Was|Were|Are|Has|Had|Did|Does)\s)"
    r"[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3}\b"
)
DEFINITION_RE = re.compile(
    r"\b(?:is|are|refers?\s+to|means?|defines?|represents?|consists?\s+of)\b", re.I)
ATTRIBUTION_INLINE_RE = re.compile(
    r"\b(?:according to|as reported by|as noted by|as stated by)\b"
    r"|(?:\w+\s+\(\d{4}\)\s+(?:found|showed|reported|demonstrated|noted|argued|claimed))", re.I,
)
FOOTNOTE_RE = re.compile(r"\[(\d{1,3})\]|\{\d{1,3}\}")
CTA_RE = re.compile(
    r"\b(?:buy now|sign up|subscribe|get started|try free|order now|click here"
    r"|limited time|act now|don't miss)\b", re.I,
)
VS_RE = re.compile(r"\bvs\.?\b|\bversus\b|\bcomparison\b", re.I)
PRO_CON_RE = re.compile(r"\b(?:pros?\s*(?:and|&)\s*cons?|advantages?\s*(?:and|&)\s*disadvantages?)\b", re.I)
NUANCE_RE = re.compile(
    r"\b(?:however|on the other hand|nevertheless|nonetheless|that said|conversely"
    r"|in contrast|although|despite|limitations? include|drawbacks?|disadvantages?"
    r"|it(?:'s| is) (?:worth noting|important to note)|not without|trade-?offs?|caveat|downside)\b", re.I,
)
NUANCE_HEADING_RE = re.compile(
    r"\b(?:limitations?|cons|disadvantages?|drawbacks?|challenges?|trade-?offs?|caveats?|risks?)\b", re.I)
SNIPPET_DEF_RE = re.compile(r"\b(?:is|are|refers?\s+to|means?|can\s+be\s+defined\s+as)\b", re.I)
QUESTION_HEADING_RE = re.compile(
    r"^(?:how\s+(?:do|can|to|does)|what\s+is|what\s+are|why\s+(?:do|is|are|does)"
    r"|when\s+(?:do|is|should)|where\s+(?:do|can|is)|which\s+(?:is|are))", re.I,
)
FIRST_PARTY_RE = re.compile(
    r"\b(?:our\s+research|we\s+analyzed|our\s+data\s+shows?|our\s+study|we\s+found"
    r"|our\s+analysis|we\s+discovered|we\s+tested|our\s+findings|we\s+measured)\b", re.I,
)
CTA_FUNNEL_RE = re.compile(
    r"\b(?:try\s+(?:it\s+)?(?:free|now)|start\s+(?:free|now|your)|sign\s+up|get\s+started"
    r"|request\s+(?:a\s+)?demo|free\s+trial|book\s+(?:a\s+)?demo)\b", re.I,
)
UPDATED_DATE_RE = re.compile(r"last\s+updated\s*:?\s*\w*\s*(\d{4})", re.I)
KG_RELATION_RE = re.compile(
    r"\b(?:is\s+a|is\s+the|is\s+an|are\s+the|was\s+founded|founded\s+(?:in|by)"
    r"|belongs?\s+to|part\s+of|consists?\s+of|includes?|developed\s+by|created\s+by"
    r"|built\s+by|maintained\s+by|owned\s+by|located\s+in|based\s+in|headquartered\s+in"
    r"|acquired\s+by|merged\s+with|partnered\s+with|invented\s+by|designed\s+by|authored\s+by"
    r"|known\s+as|also\s+called|referred\s+to\s+as|formerly|type\s+of|kind\s+of"
    r"|category\s+of|subset\s+of)\b", re.I,
)
RETRIEVAL_TRIGGER_RE = re.compile(
    r"\b(?:according\s+to|research\s+shows|studies?\s+(?:show|found|indicate|suggest)"
    r"|data\s+(?:shows?|indicates?|suggests?|reveals?)|evidence\s+(?:shows?|suggests?|indicates?)"
    r"|experts?\s+(?:say|recommend|suggest|agree|note)|as\s+of\s+\d{4}|in\s+summary"
    r"|step\s+\d+|compared\s+to|versus|unlike|for\s+example|e\.g\.|i\.e\."
    r"|best\s+practice|recommended\s+approach|industry\s+standard|FAQ"
    r"|how\s+to|what\s+is|why\s+does|when\s+to)\b", re.I,
)
GENERIC_ANCHORS = {
    "click here", "read more", "learn more", "here", "this", "link", "more",
    "continue", "go", "see more",
}
PLATFORM_DOMAINS = {
    "github": "github.com", "linkedin": "linkedin.com", "twitter": "twitter.com",
    "x": "x.com", "youtube": "youtube.com", "reddit": "reddit.com",
    "wikipedia": "wikipedia.org", "medium": "medium.com", "facebook": "facebook.com",
    "instagram": "instagram.com", "tiktok": "tiktok.com", "threads": "threads.net",
}
TTR_WINDOW, TTR_STEP, TTR_THRESHOLD = 200, 50, 0.40
KEYWORD_STUFFING_THRESHOLD = 0.025
FRONT_LOADING_DENSITY_THRESHOLD = 0.05
STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "should", "can", "could",
    "this", "that", "these", "those", "it", "its", "you", "your", "we", "our",
}


@dataclass
class MethodScore:
    name: str
    score: int
    max_score: int
    detected: bool
    detail: str = ""


@dataclass
class CitCtx:
    """Everything the 47 methods read, computed once."""
    text: str
    tree: object
    headings: list[tuple[int, str]]
    jsonld: list[dict]
    links: list[tuple[str, str]]
    domain: str
    headers: dict[str, str]
    lang: str = ""
    _c: dict = field(default_factory=dict)

    @property
    def words(self) -> list[str]:
        return self._c.setdefault("words", self.text.split())

    @property
    def word_count(self) -> int:
        return len(self.words)

    @property
    def paragraphs(self) -> list[str]:
        if "paras" not in self._c:
            self._c["paras"] = [
                re.sub(r"\s+", " ", n.text()).strip() for n in self.tree.css("p")
                if len(n.text().split()) >= 1
            ]
        return self._c["paras"]

    @property
    def sentences(self) -> list[str]:
        if "sents" not in self._c:
            self._c["sents"] = [s.strip() for s in re.split(r"(?<=[.!?])\s+", self.text) if s.strip()]
        return self._c["sents"]

    @property
    def external_links(self) -> list[tuple[str, str]]:
        return [(u, t) for u, t in self.links
                if urlparse(u).netloc.removeprefix("www.").lower() != self.domain]

    @property
    def internal_links(self) -> list[tuple[str, str]]:
        return [(u, t) for u, t in self.links
                if urlparse(u).netloc.removeprefix("www.").lower() == self.domain]

    @property
    def schema_types(self) -> set[str]:
        out = set()
        for b in self.jsonld:
            t = b.get("@type")
            out.update(t if isinstance(t, list) else [t] if t else [])
        return out

    @property
    def same_as(self) -> list[str]:
        out = []
        for b in self.jsonld:
            sa = b.get("sameAs")
            if isinstance(sa, str):
                out.append(sa)
            elif isinstance(sa, list):
                out.extend(x for x in sa if isinstance(x, str))
        return out

    def sections(self) -> list[tuple[str, str]]:
        """(heading, body) pairs — what a retriever chunks on."""
        if "sections" in self._c:
            return self._c["sections"]
        marks = []
        for lvl, h in self.headings:
            if lvl in (2, 3, 4):
                i = self.text.find(h)
                if i != -1:
                    marks.append((i, h))
        marks.sort()
        out = []
        for j, (i, h) in enumerate(marks):
            end = marks[j + 1][0] if j + 1 < len(marks) else len(self.text)
            out.append((h, self.text[i + len(h): end].strip()))
        self._c["sections"] = out
        return out

    def next_block_after(self, heading: str, limit: int = 400) -> str:
        i = self.text.find(heading)
        if i == -1:
            return ""
        return self.text[i + len(heading): i + len(heading) + limit].strip()


def _clamp(v: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(v)))


def _is_authoritative(url: str) -> bool:
    host = urlparse(url).netloc.removeprefix("www.").lower()
    return host in AUTHORITATIVE_DOMAINS or host.endswith(AUTHORITATIVE_TLDS)


def flesch_kincaid(word_count: int, sentence_count: int, syllable_count: int) -> float:
    """Flesch-Kincaid grade level. Exposed so the port can be tested directly."""
    if not word_count or not sentence_count:
        return 0.0
    return 0.39 * (word_count / sentence_count) + 11.8 * (syllable_count / word_count) - 15.59


def fk_band_score(fk: float) -> int:
    """Source band: grade 6-8 full credit, 5-10 partial, 4-12 minimal."""
    if 6 <= fk <= 8:
        return 5
    if 5 <= fk <= 10:
        return 3
    if 4 <= fk <= 12:
        return 1
    return 0


def _syllables(word: str) -> int:
    word = word.lower().strip(".,!?;:")
    if not word:
        return 0
    vowels = "aeiouy"
    n, prev = 0, False
    for ch in word:
        v = ch in vowels
        if v and not prev:
            n += 1
        prev = v
    if word.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


# --------------------------------------------------------------- the 47 methods

METHODS: list[tuple[str, int, object]] = []


def method(name: str, max_score: int):
    def deco(fn):
        METHODS.append((name, max_score, fn))
        return fn
    return deco


@method("cite_sources", 6)
def _cite_sources(c: CitCtx):
    auth = [u for u, _ in c.external_links if _is_authoritative(u)]
    cite_tags = len(c.tree.css("cite"))
    refs = sum(1 for lvl, h in c.headings if lvl in (2, 3, 4)
               and re.search(r"references?|sources?|bibliograph|citazion", h, re.I))
    s = min(len(auth) * 2 + len(c.external_links) + cite_tags * 2 + refs * 2, 6)
    return s, (len(auth) >= 2 or refs or cite_tags), f"{len(auth)} authoritative, {len(c.external_links)} external"


@method("quotation_addition", 6)
def _quotation(c: CitCtx):
    bq = c.tree.css("blockquote")
    q = len(c.tree.css("q"))
    attributed = len(QUOTE_ATTRIBUTION_RE.findall(c.text))
    with_cite = sum(1 for b in bq if b.css_first("cite") or b.css_first("footer"))
    s = min((len(bq) + q + attributed) * 2 + with_cite * 2, 6)
    return s, (len(bq) + q + attributed) >= 1, f"{len(bq)} blockquotes, {attributed} attributed"


@method("statistics_addition", 6)
def _statistics(c: CitCtx):
    m = STAT_RE.findall(c.text)
    density = len(m) / c.word_count * 1000 if c.word_count else 0
    tables = [t for t in c.tree.css("table") if len(t.css("tr")) > 1]
    data_el = len(c.tree.css("data, meter, progress"))
    s = min(int(density * 2) + len(tables) * 2 + data_el, 6)
    return s, len(m) >= 3, f"{len(m)} stats, density {density:.1f}/1k"


@method("fluency_optimization", 6)
def _fluency(c: CitCtx):
    paras = [p for p in c.paragraphs if p]
    avg = sum(len(p.split()) for p in paras) / len(paras) if paras else 0
    s = 2 if avg >= 30 else 1 if avg >= 15 else 0
    s += min(len(CONNECTIVES_RE.findall(c.text)) // 2, 2)
    items = len(c.tree.css("li")) or 1
    if len(paras) / items >= 1.5:
        s += 1
    if len(paras) >= 5:
        s += 1
    return min(s, 6), s >= 3, f"{len(paras)} paragraphs, avg {avg:.0f} words"


@method("technical_terms", 5)
def _technical(c: CitCtx):
    m = TECH_RE.findall(c.text)
    density = len(m) / c.word_count * 1000 if c.word_count else 0
    code = len(c.tree.css("code, pre"))
    s = min(int(density) + code * 2 + len(c.tree.css("abbr")) + len(c.tree.css("dfn")), 5)
    return s, (density >= 5 or code >= 1), f"density {density:.1f}/1k, {code} code blocks"


@method("authoritative_tone", 5)
def _authoritative(c: CitCtx):
    auth = len(AUTHORITY_RE.findall(c.text))
    hedges = len(HEDGE_RE.findall(c.text))
    bio = 1 if c.tree.css_first(".author-bio, .bio, [class*=author]") else 0
    schema_author = 1 if any(b.get("author") for b in c.jsonld) else 0
    creds = len(re.findall(r"\b(?:Dr\.|Prof\.|PhD|M\.D\.|MBA|MSc|BSc|CEO|CTO)\b", c.text))
    meta_author = 1 if c.tree.css_first('meta[name="author"]') else 0
    s = min(auth, 4) - min(hedges // 3, 2) + min(bio + schema_author, 3) + min(creds, 2) + meta_author
    return _clamp(s, 0, 5), s >= 3, f"{auth} authority markers, {hedges} hedges"


@method("easy_to_understand", 5)
def _easy(c: CitCtx):
    sents = c.sentences
    avg = sum(len(s.split()) for s in sents) / len(sents) if sents else 0
    s = 3 if avg <= 15 else 2 if avg <= 20 else 0
    h2 = sum(1 for lvl, _ in c.headings if lvl == 2)
    s += 2 if h2 >= 3 else 1 if h2 >= 1 else 0
    if any(lvl == 3 for lvl, _ in c.headings):
        s += 1
    s += min(sum(1 for _, h in c.headings if h.rstrip().endswith("?")), 2)
    return min(s, 5), s >= 3, f"avg sentence {avg:.0f} words, {h2} H2"


@method("unique_words", 3)
def _unique_words(c: CitCtx):
    w = [x.lower() for x in c.words if x.isalpha()]
    if len(w) < 50:
        return 0, False, "too short to measure"
    ratios = []
    for i in range(0, max(1, len(w) - TTR_WINDOW + 1), TTR_STEP):
        win = w[i:i + TTR_WINDOW]
        if len(win) >= 50:
            ratios.append(len(set(win)) / len(win))
    avg = sum(ratios) / len(ratios) if ratios else 0
    return min(int(avg * 8), 3), avg >= TTR_THRESHOLD, f"TTR {avg:.2f}"


@method("keyword_stuffing", 6)
def _keyword_stuffing(c: CitCtx):
    toks = [t.lower() for t in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", c.text)]
    if len(toks) <= 50:
        return 6, False, "too short to measure"
    counts: dict[str, int] = {}
    for t in toks:
        if t not in STOP_WORDS:
            counts[t] = counts.get(t, 0) + 1
    stuffed = [w for w, n in counts.items() if n / len(toks) > KEYWORD_STUFFING_THRESHOLD and n >= 5]
    s = 6 if not stuffed else 4 if len(stuffed) <= 1 else 2 if len(stuffed) <= 3 else 0
    # repeated 3-grams
    tri = [" ".join(toks[i:i + 3]) for i in range(len(toks) - 2)]
    seen: dict[str, int] = {}
    for g in tri:
        seen[g] = seen.get(g, 0) + 1
    repeated = sum(1 for n in seen.values() if n >= 3)
    s -= min(repeated, 2)
    first200 = toks[:200]
    if first200:
        fc: dict[str, int] = {}
        for t in first200:
            if t not in STOP_WORDS:
                fc[t] = fc.get(t, 0) + 1
        if sum(1 for n in fc.values() if n / len(first200) > FRONT_LOADING_DENSITY_THRESHOLD) >= 2:
            s -= 1
    return _clamp(s, 0, 6), len(stuffed) >= 2 or repeated >= 1, f"{len(stuffed)} stuffed terms"


@method("answer_first", 5)
def _answer_first(c: CitCtx):
    h2s = [h for lvl, h in c.headings if lvl == 2]
    if not h2s:
        return 0, False, "no H2 sections"
    hits = sum(1 for h in h2s if FACT_RE.search(c.next_block_after(h, 150)))
    ratio = hits / len(h2s)
    return min(int(ratio * 8), 5), ratio >= 0.3, f"{hits}/{len(h2s)} sections open with a fact"


@method("passage_density", 5)
def _passage_density(c: CitCtx):
    cands = [p for p in c.paragraphs if len(p.split()) >= 10]
    if not cands:
        return 0, False, "no substantive paragraphs"
    dense = [p for p in cands if 50 <= len(p.split()) <= 150 and re.search(r"\d", p)]
    ratio = len(dense) / len(cands)
    return min(int(ratio * 10), 5), len(dense) >= 2, f"{len(dense)} dense passages"


@method("readability", 8)
def _readability(c: CitCtx):
    # Flesch-Kincaid and its English syllable rules mean nothing on other
    # languages (Italian's final "e" is not silent), so other languages are left
    # out of the score rather than failed by a formula that cannot read them.
    if c.lang not in ("", "en"):
        return None, False, f"not scored: the formula is English-only, page is '{c.lang}'"
    sents, words = c.sentences, [w for w in c.words if w.isalpha()]
    if not sents or not words:
        return 0, False, "no prose"
    syl = sum(_syllables(w) for w in words)
    fk = flesch_kincaid(len(words), len(sents), syl)
    s = fk_band_score(fk)
    secs = [len(b.split()) for _, b in c.sections()]
    optimal = sum(1 for n in secs if 100 <= n <= 150)
    if secs:
        s += min(int(optimal / len(secs) * 3), 3)
    return min(s, 8), 6 <= fk <= 10, f"Flesch-Kincaid grade {fk:.1f}"


@method("faq_in_content", 6)
def _faq(c: CitCtx):
    n = 0
    for lvl, h in c.headings:
        if h.rstrip().endswith("?") and len(c.next_block_after(h, 200)) >= 20:
            n += 1
    for d in c.tree.css("details"):
        if d.css_first("summary") and len(d.text()) >= 20:
            n += 1
    for dt in c.tree.css("dt"):
        if "?" in dt.text():
            n += 1
    s = 6 if n >= 5 else 4 if n >= 3 else 2 if n >= 1 else 0
    return s, n >= 1, f"{n} Q&A pairs"


@method("image_alt_quality", 5)
def _image_alt(c: CitCtx):
    # Decorative images (alt="") carry nothing to describe, so they are left out.
    imgs = [i for i in c.tree.css("img") if (i.attributes.get("alt") or "").strip()
            or "alt" not in i.attributes]
    if not imgs:
        return 3, False, "no content images (neutral)"
    alts = [(i.attributes.get("alt") or "").strip() for i in imgs]
    missing = sum(1 for a in alts if not a)
    descriptive = sum(1 for a in alts if len(a) > 10 and not GENERIC_ALT_RE.match(a))
    ratio = descriptive / len(imgs)
    s = 5 if ratio >= 0.8 else 3 if ratio >= 0.5 else 2 if ratio >= 0.2 else (1 if missing == 0 else 0)
    return s, ratio >= 0.5, f"{descriptive}/{len(imgs)} descriptive alt"


@method("content_freshness", 6)
def _freshness(c: CitCtx):
    dates = []
    for b in c.jsonld:
        for k in ("dateModified", "datePublished"):
            if isinstance(b.get(k), str):
                dates.append(b[k])
    for n in c.tree.css("time[datetime]"):
        dates.append(n.attributes.get("datetime", ""))
    age = None
    for d in dates:
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            a = (datetime.now(timezone.utc) - dt).days
            age = a if age is None else min(age, a)
        except ValueError:
            continue
    if age is None:
        s = 1
    else:
        s = 4 if age < 90 else 3 if age < 180 else 2 if age < 365 else 0
    if re.search(rf"\b{datetime.now(timezone.utc).year}\b", c.text):
        s += 2
    return min(s, 6), age is not None and age < 365, (f"{age}d old" if age is not None else "no date signal")


@method("citability_density", 7)
def _citability_density(c: CitCtx):
    cands = [p for p in c.paragraphs if len(p.split()) >= 10]
    if not cands:
        return 0, False, "no substantive paragraphs"
    def facts(p: str) -> int:
        return len(CITABLE_NUMERIC_RE.findall(p)) + len(PROPER_NAME_RE.findall(p))
    dense = [p for p in cands if facts(p) >= 2]
    ratio = len(dense) / len(cands)
    s = 7 if ratio >= 0.5 else 5 if ratio >= 0.3 else 3 if ratio >= 0.15 else (1 if dense else 0)
    return s, len(dense) >= 2, f"{len(dense)}/{len(cands)} fact-dense paragraphs"


@method("definition_patterns", 5)
def _definitions(c: CitCtx):
    heads = [h for lvl, h in c.headings if lvl in (1, 2)]
    if not heads:
        return 0, False, "no headings"
    hits = sum(1 for h in heads if DEFINITION_RE.search(c.next_block_after(h, 150)))
    ratio = hits / len(heads)
    s = 5 if ratio >= 0.6 else 4 if ratio >= 0.4 else 3 if ratio >= 0.2 else (2 if hits else 0)
    return s, hits >= 1, f"{hits}/{len(heads)} sections define their subject"


@method("format_mix", 5)
def _format_mix(c: CitCtx):
    base = sum([len(c.tree.css("p")) >= 3, bool(c.tree.css("ul, ol")), bool(c.tree.css("table"))])
    bonus = sum([bool(c.tree.css("pre, code")), bool(c.tree.css("blockquote"))])
    s = 4 + min(bonus, 1) if base == 3 else 2 + min(bonus, 1) if base == 2 else 1 if base == 1 else 0
    return min(s, 5), base >= 2, f"{base}/3 base formats"


@method("attribution_completeness", 5)
def _attribution(c: CitCtx):
    inline = len(ATTRIBUTION_INLINE_RE.findall(c.text))
    footnotes = len(FOOTNOTE_RE.findall(c.text)) + sum(
        1 for s in c.tree.css("sup") if s.text().strip().isdigit())
    s = min(inline * 2 + footnotes, 5)
    return s, inline >= 1 or footnotes >= 2, f"{inline} inline attributions, {footnotes} footnotes"


@method("no_negative_signals", 5)
def _no_negative(c: CitCtx):
    pen = 0
    ctas = len(CTA_RE.findall(c.text))
    if c.word_count and ctas / c.word_count > 0.005:
        pen += 2
    if any(lvl == 2 for lvl, _ in c.headings) and c.word_count < 300:
        pen += 2
    if not any(b.get("author") for b in c.jsonld) and not c.tree.css_first("[rel=author], .author"):
        pen += 1
    seen: dict[str, int] = {}
    for s in c.sentences:
        if len(s) > 20:
            seen[s] = seen.get(s, 0) + 1
    pen += min(sum(1 for n in seen.values() if n >= 3), 2)
    return _clamp(5 - pen, 0, 5), pen >= 2, f"{pen} negative signals"


@method("comparison_content", 4)
def _comparison(c: CitCtx):
    vs = sum(1 for _, h in c.headings if VS_RE.search(h))
    pc = sum(1 for _, h in c.headings if PRO_CON_RE.search(h)) + (1 if PRO_CON_RE.search(c.text) else 0)
    tables = c.tree.css("table")
    large = sum(1 for t in tables if len(t.css("tr")) > 3 and len(t.css("tr")[0].css("td, th")) > 2)
    s = min(vs, 2) + min(pc, 2) + min(len(tables) + large, 2)
    return min(s, 4), s >= 1, f"{vs} vs-headings, {len(tables)} tables"


@method("eeat_signals", 7)
def _eeat(c: CitCtx):
    hay = " ".join(f"{u} {t}" for u, t in c.links).lower()
    trust = sum(1 for kws in (("privacy", "cookie"), ("terms", "tos"), ("about",), ("contact",))
                if any(k in hay for k in kws))
    s = min(trust, 3)
    bio = c.tree.css_first(".author-bio, .bio")
    if bio and len(bio.text()) > 50 and re.search(r"\d+\s+(?:years|experience)", bio.text(), re.I):
        s += 1
    for b in c.jsonld:
        a = b.get("author")
        if isinstance(a, dict) and a.get("@type") == "Person":
            s += 1
            if a.get("sameAs"):
                s += 1
            break
    canon = c.tree.css_first('link[rel="canonical"]')
    if (canon and canon.attributes.get("href", "").startswith("https")) or \
       (c.tree.css_first('meta[property="og:url"]') is not None):
        s += 1
    return min(s, 7), s >= 2, f"{trust} trust links"


@method("no_content_decay", 5)
def _no_decay(c: CitCtx):
    year = datetime.now(timezone.utc).year
    old = {int(y) for y in re.findall(r"\b(20[0-2]\d)\b", c.text) if int(y) < year - 1}
    current_ref = bool(re.search(rf"\b{year}\b", c.text))
    recent = any(k in str(c.jsonld) for k in ("dateModified",))
    pen = 0
    if old and not current_ref and not recent:
        pen += min(len(old), 3)
    pen += len([m for m in UPDATED_DATE_RE.findall(c.text) if int(m) < year - 1])
    return _clamp(5 - pen, 0, 5), pen >= 2, f"{len(old)} stale year references"


@method("boilerplate_ratio", 4)
def _boilerplate(c: CitCtx):
    total = len(c.text)
    if total < 50:
        return 2, False, "too little text to measure"
    main = c.tree.css_first("main, article, [role=main]")
    ratio = len(re.sub(r"\s+", " ", main.text()).strip()) / total if main else None
    if ratio is None:
        chrome = sum(len(n.text()) for n in c.tree.css("nav, footer, header"))
        ratio = max(0.0, 1 - chrome / total)
    s = 4 if ratio >= 0.60 else 3 if ratio >= 0.45 else 2 if ratio >= 0.30 else 1 if ratio >= 0.15 else 0
    return s, ratio >= 0.45, f"{ratio:.0%} main content"


@method("nuance_signals", 3)
def _nuance(c: CitCtx):
    m = len(NUANCE_RE.findall(c.text))
    heads = sum(1 for _, h in c.headings if NUANCE_HEADING_RE.search(h))
    total = m + heads * 2
    s = 3 if total >= 5 else 2 if total >= 3 else 1 if total >= 1 else 0
    return s, total >= 2, f"{m} nuance markers, {heads} headings"


@method("snippet_ready", 4)
def _snippet_ready(c: CitCtx):
    heads = [h for lvl, h in c.headings if lvl in (2, 3, 4)]
    if not heads:
        return 0, False, "no headings"
    hits = 0
    for h in heads:
        blk = c.next_block_after(h, 300)
        first = re.split(r"(?<=[.!?])\s+", blk)[0] if blk else ""
        if h.rstrip().endswith("?") and 5 <= len(first.split()) <= 60:
            hits += 1
        elif SNIPPET_DEF_RE.search(blk[:150]):
            hits += 1
    ratio = hits / len(heads)
    s = 4 if ratio >= 0.5 else 3 if ratio >= 0.3 else 2 if ratio >= 0.15 else (1 if hits else 0)
    return s, hits >= 1, f"{hits}/{len(heads)} snippet-ready sections"


@method("chunk_quotability", 4)
def _chunk_quotability(c: CitCtx):
    cands = [p for p in c.paragraphs if 50 <= len(p.split()) <= 150]
    if not cands:
        return 0, False, "no paragraphs in the 50-150 word band"
    quotable = [p for p in cands if CITABLE_NUMERIC_RE.search(p)]
    ratio = len(quotable) / len(cands)
    s = 4 if ratio >= 0.5 else 3 if ratio >= 0.3 else 2 if ratio >= 0.15 else (1 if quotable else 0)
    return s, len(quotable) >= 1, f"{len(quotable)}/{len(cands)} quotable chunks"


@method("blog_structure", 4)
def _blog_structure(c: CitCtx):
    if not ({"Article", "BlogPosting", "NewsArticle"} & c.schema_types):
        return 0, False, "no Article schema"
    s = 0
    for b in c.jsonld:
        if b.get("datePublished") or b.get("dateModified"):
            s += 1
            break
    if any(b.get("author") for b in c.jsonld):
        s += 1
    if c.tree.css_first(".author-bio, .bio, [class*=author]"):
        s += 1
    if any(b.get("articleSection") or b.get("keywords") for b in c.jsonld) or \
       c.tree.css_first('meta[property="article:tag"]'):
        s += 1
    return min(s, 4), s >= 2, f"{s}/4 article signals"


@method("shopping_readiness", 3)
def _shopping(c: CitCtx):
    prod = next((b for b in c.jsonld if b.get("@type") == "Product"), None)
    if not prod:
        return 0, False, "no Product schema"
    offers = prod.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    s = 0
    if isinstance(offers, dict) and offers.get("price") and offers.get("availability"):
        s += 1
    if prod.get("aggregateRating"):
        s += 1
        ar = prod["aggregateRating"]
        if isinstance(ar, dict) and (ar.get("reviewCount") or ar.get("ratingCount")):
            s += 1
    return min(s, 3), s >= 1, f"{s}/3 commerce signals"


@method("chatgpt_shopping", 3)
def _chatgpt_shopping(c: CitCtx):
    prod = next((b for b in c.jsonld if b.get("@type") == "Product"), None)
    if not prod:
        return 0, False, "no Product schema"
    offers = prod.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    have = sum([
        bool(prod.get("name")), bool(prod.get("image")), bool(prod.get("brand")),
        bool(isinstance(offers, dict) and offers.get("price")),
        bool(isinstance(offers, dict) and offers.get("availability")),
    ])
    s = 3 if have >= 5 else 2 if have >= 3 else 1 if have >= 1 else 0
    return s, have >= 3, f"{have}/5 required fields"


@method("voice_search_ready", 3)
def _voice(c: CitCtx):
    qh = [h for _, h in c.headings if h.rstrip().endswith("?") or QUESTION_HEADING_RE.match(h)]
    s = 1 if len(qh) >= 2 else 0
    if any(len(c.next_block_after(h, 400).split()) < 60 for h in qh):
        s += 1
    if "speakable" in str(c.jsonld):
        s += 1
    return min(s, 3), s >= 2 or len(qh) >= 2, f"{len(qh)} question headings"


@method("multi_platform", 4)
def _multi_platform(c: CitCtx):
    found = {name for name, dom in PLATFORM_DOMAINS.items()
             if any(dom in u for u in c.same_as)}
    s = 4 if len(found) >= 5 else 2 if len(found) >= 3 else 0
    return s, len(found) >= 3, f"{len(found)} platforms in sameAs"


@method("entity_disambiguation", 3)
def _entity_disambig(c: CitCtx):
    s = 0
    title = c.tree.css_first("title")
    if title:
        parts = [p.strip() for p in re.split(r"\s*[|\-–—·]\s*", title.text()) if p.strip()]
        names = {b.get("name", "").lower() for b in c.jsonld if isinstance(b.get("name"), str)}
        if names and any(p.lower() in names for p in parts):
            s += 1
    first_paras = c.paragraphs[:3]
    if any(DEFINITION_RE.search(p) for p in first_paras):
        s += 1
    if len(c.same_as) > 3:
        s += 1
    return min(s, 3), s >= 2, f"{s}/3 disambiguation signals"


@method("first_party_data", 4)
def _first_party(c: CitCtx):
    m = len(FIRST_PARTY_RE.findall(c.text))
    s = 2 if m >= 2 else 1 if m >= 1 else 0
    if re.search(r"\b(?:we|our team|our company)\s+\w+\s+\d+", c.text, re.I):
        s += 1
    if any(re.fullmatch(r"(?:methodology|methods|how we tested)", h.strip(), re.I)
           for _, h in c.headings):
        s += 1
    return min(s, 4), s >= 2, f"{m} first-party data claims"


@method("no_stale_data", 4)
def _no_stale(c: CitCtx):
    year = datetime.now(timezone.utc).year
    pen = 0
    copyright_years = [int(y) for y in re.findall(r"©\s*(?:\d{4}\s*[-–]\s*)?(\d{4})", c.text)]
    if copyright_years and max(copyright_years) < year - 1:
        pen += 2
    stale_refs = [int(y) for y in re.findall(r"(?:as of|in|nel)\s+(20[0-2]\d)", c.text, re.I)
                  if int(y) < year - 1]
    pen += 2 if len(stale_refs) >= 3 else 1 if stale_refs else 0
    return _clamp(4 - pen, 0, 4), pen >= 1, f"{len(stale_refs)} stale references"


@method("social_proof", 3)
def _social_proof(c: CitCtx):
    s = 0
    if c.tree.css_first("[class*=testimonial], [class*=review], [class*=customer-quote]") or \
       re.search(r"\b(?:as seen in|as featured in|featured by|trusted by)\b", c.text, re.I):
        s += 1
    for b in c.jsonld:
        ar = b.get("aggregateRating")
        if isinstance(ar, dict):
            try:
                if int(ar.get("reviewCount", 0)) > 10:
                    s += 1
                    break
            except (TypeError, ValueError):
                pass
    if c.tree.css_first("[class*=partner], [class*=badge], [class*=award], [class*=client-logo]"):
        s += 1
    return min(s, 3), s >= 1, f"{s}/3 social proof signals"


@method("accessibility_signals", 3)
def _accessibility(c: CitCtx):
    s = 0
    if sum(1 for t in ("main", "nav", "header", "footer") if c.tree.css_first(t)) >= 3:
        s += 1
    if any(c.tree.css_first(f'[role="{r}"]') for r in ("main", "navigation", "banner", "contentinfo")):
        s += 1
    if c.tree.css_first('a[href="#main"], a[href="#content"], a[href="#main-content"]') or \
       re.search(r"skip to", c.text[:500], re.I):
        s += 1
    return min(s, 3), s >= 1, f"{s}/3 accessibility landmarks"


@method("conversion_funnel", 3)
def _funnel(c: CitCtx):
    s = 0
    if any(CTA_FUNNEL_RE.search(n.text()) for n in c.tree.css("a, button")):
        s += 1
    hrefs = " ".join(u.lower() for u, _ in c.links)
    if re.search(r"pricing|plans|prezzi", hrefs):
        s += 1
    if re.search(r"contact|mailto:|contatti", hrefs):
        s += 1
    return min(s, 3), s >= 1, f"{s}/3 funnel signals"


@method("temporal_coherence", 4)
def _temporal(c: CitCtx):
    raw = []
    for b in c.jsonld:
        for k in ("dateModified", "datePublished"):
            if isinstance(b.get(k), str):
                raw.append(b[k])
    for n in c.tree.css('meta[property^="article:"]'):
        if n.attributes.get("content"):
            raw.append(n.attributes["content"])
    parsed = []
    for d in raw:
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            parsed.append(dt.replace(tzinfo=dt.tzinfo or timezone.utc))
        except ValueError:
            continue
    if len(parsed) >= 2:
        spread = (max(parsed) - min(parsed)).days
        s = 4 if spread <= 30 else 2 if spread <= 90 else 0
        return s, s >= 2, f"{len(parsed)} dates, {spread}d spread"
    return (1, False, "one date") if len(parsed) == 1 else (0, False, "no dates")


@method("anchor_text_quality", 3)
def _anchor_quality(c: CitCtx):
    internal = [t for _, t in c.internal_links if t]
    if not internal:
        return 2, False, "no internal links (neutral)"
    good = sum(1 for t in internal if t.strip().lower() not in GENERIC_ANCHORS)
    ratio = good / len(internal)
    s = 3 if ratio >= 0.8 else 2 if ratio >= 0.5 else 1 if ratio > 0 else 0
    return s, ratio >= 0.8, f"{good}/{len(internal)} descriptive anchors"


@method("international_geo", 3)
def _international(c: CitCtx):
    hreflang = c.tree.css('link[rel="alternate"][hreflang]')
    if not hreflang:
        return 0, False, "no hreflang (not penalised)"
    s = 2 if len(hreflang) >= 3 else 1
    if any(b.get("inLanguage") for b in c.jsonld):
        s += 1
    return min(s, 3), True, f"{len(hreflang)} hreflang alternates"


@method("crawl_budget", 3)
def _crawl_budget(c: CitCtx):
    s, notes = 3, []
    robots = c.tree.css_first('meta[name="robots"], meta[http-equiv="x-robots-tag"]')
    content = (robots.attributes.get("content", "") if robots else "").lower()
    if "noindex" in content:
        s -= 2
        notes.append("noindex")
    if "nofollow" in content:
        s -= 1
        notes.append("nofollow")
    if "noai" in content or "noimageai" in content:
        s -= 1
        notes.append("noai")
    return _clamp(s, 0, 3), not notes, ", ".join(notes) or "no blocking directives"


@method("answer_capsule", 4)
def _answer_capsule(c: CitCtx):
    weak = ("however", "but", "although", "moreover", "furthermore", "additionally", "nevertheless")
    cands = [p for p in c.paragraphs if 30 <= len(p.split()) <= 120]
    if not cands:
        return 0, False, "no paragraphs in the 30-120 word band"
    caps = [p for p in cands
            if p.rstrip().endswith((".", "!", "?"))
            and CITABLE_NUMERIC_RE.search(p)
            and not p.lower().startswith(weak)]
    ratio = len(caps) / len(cands)
    s = 4 if ratio >= 0.4 else 3 if ratio >= 0.25 else 2 if ratio >= 0.15 else (1 if caps else 0)
    return s, len(caps) >= 2, f"{len(caps)} answer capsules"


@method("token_efficiency", 3)
def _token_efficiency(c: CitCtx):
    if c.word_count < 20:
        return 1, False, "too little text"
    main = c.tree.css_first("main, article, [role=main]")
    content_words = len(main.text().split()) if main else c.word_count
    ratio = min(1.0, content_words / c.word_count)
    s = 3 if ratio >= 0.75 else 2 if ratio >= 0.60 else 1 if ratio >= 0.45 else 0
    return s, ratio >= 0.60, f"{ratio:.0%} signal to boilerplate"


@method("entity_resolution", 4)
def _entity_resolution(c: CitCtx):
    s = 0
    typed_named = [b for b in c.jsonld if b.get("@type") and b.get("name")]
    if any(b.get("description") for b in typed_named):
        s += 1
    if any(len(b.get("sameAs") or []) >= 2 for b in c.jsonld if isinstance(b.get("sameAs"), list)):
        s += 1
    if typed_named:
        s += 1
    if c.paragraphs and re.search(r"\b(?:is|are|refers to)\s+(?:a|an|the|one of|defined as)\b",
                                  c.paragraphs[0], re.I):
        s += 1
    return min(s, 4), s >= 2, f"{s}/4 entity signals"


@method("kg_density", 4)
def _kg_density(c: CitCtx):
    rel = len(KG_RELATION_RE.findall(c.text))
    density = rel / c.word_count * 500 if c.word_count else 0
    schema_rel = sum(1 for k in ("author", "creator", "publisher", "founder", "parentOrganization",
                                 "memberOf", "worksFor", "location", "address", "brand",
                                 "manufacturer", "isPartOf", "hasPart", "mainEntity")
                     if any(b.get(k) for b in c.jsonld))
    if density >= 8 or (density >= 5 and schema_rel >= 3):
        s = 4
    elif density >= 5 or (density >= 3 and schema_rel >= 2):
        s = 3
    elif density >= 3 or schema_rel >= 2:
        s = 2
    elif rel >= 2 or schema_rel >= 1:
        s = 1
    else:
        s = 0
    return s, s >= 2, f"{rel} relations, {density:.1f}/500 words"


@method("retrieval_triggers", 4)
def _retrieval_triggers(c: CitCtx):
    unique = {m.lower() for m in RETRIEVAL_TRIGGER_RE.findall(c.text)}
    qh = sum(1 for _, h in c.headings if h.rstrip().endswith("?") or QUESTION_HEADING_RE.match(h))
    n = len(unique)
    if n >= 8 and qh >= 2:
        s = 4
    elif n >= 6 or (n >= 4 and qh >= 2):
        s = 3
    elif n >= 4 or (n >= 2 and qh >= 1):
        s = 2
    elif n >= 2 or qh >= 1:
        s = 1
    else:
        s = 0
    return s, s >= 2, f"{n} distinct retrieval triggers"


MAX_POSSIBLE = sum(m[1] for m in METHODS)


def run(ctx) -> dict:
    """Score every method. `ctx` is an audit.checks.Ctx."""
    c = CitCtx(
        text=ctx.body_text, tree=ctx.tree, headings=ctx.headings, jsonld=ctx.jsonld,
        links=ctx.links, domain=ctx.snap.domain.lower(), headers=ctx.snap.headers,
        lang=getattr(ctx, "lang", ""),
    )
    results = []
    for name, max_score, fn in METHODS:
        try:
            score_, detected, detail = fn(c)
        except Exception as e:  # a single bad method must not sink the audit
            score_, detected, detail = 0, False, f"error: {type(e).__name__}"
        if score_ is None:
            # Not applicable to this page: out of both the score and the maximum.
            results.append(MethodScore(name, 0, 0, False, detail))
            continue
        results.append(MethodScore(name, _clamp(score_, 0, max_score), max_score, bool(detected), detail))

    raw = sum(m.score for m in results)
    possible = sum(m.max_score for m in results)
    return {
        "score": round(100 * raw / possible) if possible else 0,
        "raw": raw,
        "max_possible": possible,
        "methods": [
            {"name": m.name, "score": m.score, "max_score": m.max_score,
             "detected": m.detected, "detail": m.detail}
            for m in results
        ],
    }
