"""AI + search crawler taxonomy.

Ported from geo-optimizer's AI_BOTS/BOT_TIERS, which encode a distinction most
audit tools get wrong: a *training* token and a *search* token are different
things. Blocking GPTBot says nothing about whether ChatGPT can cite you — that
is OAI-SearchBot. Google-Extended controls Gemini/Vertex training only and is
NOT a lever on AI Overviews eligibility, which rides on plain Googlebot.

Tiers:
  training - governs model training corpora. A licensing choice, not a visibility one.
  search   - governs whether the engine can retrieve and CITE you. This is what matters.
  user     - user-triggered fetches. Several ignore robots.txt entirely by design.
"""
from __future__ import annotations

# name -> (tier, operator-facing description, obeys_robots)
BOTS: dict[str, tuple[str, str, bool]] = {
    # OpenAI
    "GPTBot": ("training", "OpenAI: ChatGPT model training", True),
    "OAI-SearchBot": ("search", "OpenAI: ChatGPT search citations", True),
    "ChatGPT-User": ("user", "OpenAI: ChatGPT on-demand fetch", False),
    # Anthropic
    "ClaudeBot": ("training", "Anthropic: Claude model training", True),
    "Claude-SearchBot": ("search", "Anthropic: Claude search citations", True),
    "Claude-User": ("user", "Anthropic: Claude on-demand fetch", False),
    # Perplexity
    "PerplexityBot": ("search", "Perplexity: index builder", True),
    "Perplexity-User": ("user", "Perplexity: citation fetch on demand", False),
    # Google
    "Googlebot": ("search", "Google: Search AND AI Overviews", True),
    "Google-Extended": ("training", "Google: Gemini/Vertex training opt-out (not a crawler)", True),
    "Google-CloudVertexBot": ("training", "Google: Vertex AI owner-requested crawls", True),
    # Microsoft / Apple
    "Bingbot": ("search", "Microsoft: Bing and Copilot search", True),
    "Applebot": ("search", "Apple: Siri, Spotlight, Safari discoverability", True),
    "Applebot-Extended": ("training", "Apple: Apple Intelligence training opt-out", True),
    # Other search
    "DuckAssistBot": ("search", "DuckDuckGo: DuckAssist", True),
    "YouBot": ("search", "You.com", True),
    "Amazonbot": ("search", "Amazon: Alexa", True),
    "xAI-Bot": ("search", "xAI: Grok", True),
    # Other training
    "cohere-ai": ("training", "Cohere: language models", True),
    "Bytespider": ("training", "ByteDance", True),
    "meta-externalagent": ("training", "Meta: model training", True),
    "PetalBot": ("training", "Huawei Petal", True),
    "AI2Bot": ("training", "Allen Institute", True),
    "AI2Bot-Dolma": ("training", "Allen Institute: Dolma corpus", True),
    "CCBot": ("training", "Common Crawl: open dataset", True),
    # Other user-triggered
    "Meta-ExternalFetcher": ("user", "Meta: on-demand fetch", False),
    "facebookexternalhit": ("user", "Meta: link preview fetch", False),
}

TRAINING = {b for b, (t, _, _) in BOTS.items() if t == "training"}
SEARCH = {b for b, (t, _, _) in BOTS.items() if t == "search"}
USER = {b for b, (t, _, _) in BOTS.items() if t == "user"}

# The five that actually decide whether an answer engine can cite you.
# Deliberately excludes ClaudeBot and Google-Extended: both are training-only
# tokens and scoring them as citability signals is the single most common
# error in AI-SEO tooling.
CITATION_BOTS = {"OAI-SearchBot", "Claude-SearchBot", "PerplexityBot", "Googlebot", "Applebot"}

# Bots worth spending a live HTTP probe on. Probing all 27 would be 27 requests
# for little extra signal, so we probe the ones a block would actually cost you.
PROBE_BOTS = CITATION_BOTS | {"GPTBot", "ClaudeBot", "Bingbot"}

# Real user-agent strings, so a WAF sees what it would really see.
USER_AGENTS: dict[str, str] = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "Claude-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +https://www.anthropic.com/claude-searchbot)",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Applebot": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.1 Safari/605.1.15 (Applebot/0.1; +http://www.apple.com/go/applebot)",
    "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
}

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# A WAF rarely returns a clean 403 — it returns 200 with a challenge page.
#
# Two tiers, because the generic tier is unsafe on its own. Words like
# "captcha", "blocked" and "forbidden" appear in ordinary prose: a security
# vendor's homepage, a cookie banner, a post about bot filtering. Treating
# those as a challenge at HTTP 200 marks a perfectly reachable page as
# edge-blocked and silently suppresses the AI score. Generic words therefore
# only count alongside an error status; vendor fingerprints stand alone.
CHALLENGE_FINGERPRINTS = (
    "cf-browser-verification", "challenge-platform", "cf-chl", "cf_chl",
    "just a moment", "checking your browser", "verify you are human",
    "px-captcha", "_incapsula_resource", "datadome",
)
CHALLENGE_GENERIC = (
    "ray id", "access denied", "bot detection", "captcha", "blocked", "forbidden",
)


def looks_challenged(body: str, status: int | None) -> bool:
    """True when the body is an interstitial rather than the real page."""
    head = body[:4000].lower()
    if any(m in head for m in CHALLENGE_FINGERPRINTS):
        return True
    return status is not None and status >= 400 and any(m in head for m in CHALLENGE_GENERIC)
# 402 is the one people miss. Cloudflare's pay-per-crawl and the x402
# micropayment protocol both answer AI crawlers with "Payment Required" while
# serving Googlebot normally, so a site can rank perfectly and be completely
# uncitable. Treating it as reachable understates exactly what we exist to find.
BLOCKED_STATUSES = {402, 403, 429, 451, 503}
# A bot response far shorter than the browser's is a soft block even at HTTP 200.
CONTENT_RATIO_BLOCK = 0.30

CDN_HEADERS = (
    "cf-ray", "cf-cache-status", "x-amz-cf-id", "x-amz-request-id",
    "x-akamai-transformed", "x-cdn", "x-served-by", "x-vercel-id",
)


def tier(bot: str) -> str:
    return BOTS.get(bot, ("unknown", "", True))[0]


def describe(bot: str) -> str:
    return BOTS.get(bot, ("unknown", bot, True))[1]


def obeys_robots(bot: str) -> bool:
    return BOTS.get(bot, ("unknown", "", True))[2]
