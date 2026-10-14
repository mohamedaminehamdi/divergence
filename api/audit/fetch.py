"""Fetch everything the audit needs about a URL, in one pass."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

from . import bots
from .bots import BROWSER_UA, CITATION_BOTS, PROBE_BOTS

# Kept as an alias: several checks iterate the probed set by name.
AI_BOTS = {b: bots.describe(b) for b in PROBE_BOTS}

TIMEOUT = httpx.Timeout(15.0, connect=8.0)


@dataclass
class BotProbe:
    bot: str
    status: int | None
    blocked_by_robots: bool
    body_len: int = 0
    challenge: bool = False
    browser_body_len: int = 0
    error: str | None = None

    @property
    def tier(self) -> str:
        return bots.tier(self.bot)

    @property
    def is_citation_bot(self) -> bool:
        return self.bot in CITATION_BOTS

    @property
    def starved(self) -> bool:
        """Served far less content than a browser. A soft block at HTTP 200."""
        if self.status != 200 or not self.browser_body_len:
            return False
        return self.body_len < self.browser_body_len * bots.CONTENT_RATIO_BLOCK

    @property
    def blocked_by_edge(self) -> bool:
        """A WAF rarely returns a clean 403; it returns a challenge page at 200."""
        if self.status is None:
            return False
        return self.status in bots.BLOCKED_STATUSES or self.challenge or self.starved

    @property
    def reachable(self) -> bool:
        return not self.blocked_by_robots and not self.blocked_by_edge


@dataclass
class SiteSnapshot:
    url: str
    final_url: str
    status: int
    html: str
    headers: dict[str, str]
    ttfb_ms: float
    bytes: int
    robots_txt: str | None
    llms_txt: str | None
    sitemap_urls: list[str]
    robots_sitemap_refs: list[str]
    bot_probes: list[BotProbe] = field(default_factory=list)
    cdn: str | None = None

    @property
    def origin(self) -> str:
        p = urlparse(self.final_url)
        return f"{p.scheme}://{p.netloc}"

    @property
    def domain(self) -> str:
        return urlparse(self.final_url).netloc.removeprefix("www.")


def _robots_allows(robots: str | None, bot: str, path: str = "/") -> bool:
    """Minimal robots.txt evaluation for one agent.

    Longest-match wins per the spec; Allow beats Disallow at equal length.
    A missing robots.txt means allowed.
    """
    if not robots:
        return True

    groups: dict[str, list[tuple[str, str]]] = {}
    current: list[str] = []
    # A blank line ends a group; consecutive User-agent lines share one rule block.
    expecting_agents = False
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            current = []
            expecting_agents = False
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if not expecting_agents:
                current = []
            current.append(value.lower())
            groups.setdefault(value.lower(), [])
            expecting_agents = True
        elif field in ("allow", "disallow") and current:
            expecting_agents = False
            for agent in current:
                groups.setdefault(agent, []).append((field, value))

    rules = groups.get(bot.lower())
    if rules is None:
        rules = groups.get("*")
    if not rules:
        return True

    best: tuple[int, str] | None = None
    for kind, pattern in rules:
        if not pattern:
            # "Disallow:" with an empty value explicitly allows everything.
            if kind == "disallow" and (best is None or best[0] == 0):
                best = (0, "allow")
            continue
        if _path_matches(pattern, path):
            length = len(pattern)
            if best is None or length > best[0] or (length == best[0] and kind == "allow"):
                best = (length, kind)

    return best is None or best[1] == "allow"


def _path_matches(pattern: str, path: str) -> bool:
    """robots.txt wildcard matching: * is any run, $ anchors the end."""
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    parts = pattern.split("*")
    if not path.startswith(parts[0]):
        return False
    pos = len(parts[0])
    for part in parts[1:]:
        if not part:
            continue
        idx = path.find(part, pos)
        if idx == -1:
            return False
        pos = idx + len(part)
    return not anchored or pos == len(path)


async def _get(
    client: httpx.AsyncClient, url: str, ua: str = BROWSER_UA, emit=None, label: str | None = None
) -> httpx.Response | None:
    """Every outbound request goes through here, so this is the one place that
    needs to report progress. Events describe fetches that actually happened."""
    started = time.perf_counter()
    try:
        r = await client.get(url, headers={"User-Agent": ua})
    except httpx.HTTPError as e:
        if emit:
            emit({"type": "fetch", "url": url, "label": label, "status": None,
                  "ms": round((time.perf_counter() - started) * 1000), "error": type(e).__name__})
        return None
    if emit:
        emit({"type": "fetch", "url": url, "label": label, "status": r.status_code,
              "ms": round((time.perf_counter() - started) * 1000)})
    return r


async def _probe_bot(
    client: httpx.AsyncClient, url: str, bot: str, robots: str | None, path: str,
    browser_len: int, emit=None
) -> BotProbe:
    allowed = _robots_allows(robots, bot, path)
    resp = await _get(client, url, ua=bots.USER_AGENTS.get(bot, f"{bot}/1.0"),
                      emit=emit, label=bot)
    if resp is None:
        return BotProbe(bot, None, not allowed, error="request failed")
    body = resp.text
    challenge = bots.looks_challenged(body, resp.status_code)
    return BotProbe(
        bot, resp.status_code, not allowed,
        body_len=len(body), challenge=challenge, browser_body_len=browser_len,
    )


def _detect_cdn(headers: dict[str, str]) -> str | None:
    for h in bots.CDN_HEADERS:
        if h in headers:
            return {"cf-ray": "Cloudflare", "cf-cache-status": "Cloudflare",
                    "x-amz-cf-id": "CloudFront", "x-akamai-transformed": "Akamai",
                    "x-vercel-id": "Vercel", "x-served-by": "Fastly"}.get(h, headers.get("server") or h)
    server = headers.get("server", "").lower()
    for name in ("cloudflare", "akamai", "fastly", "vercel", "netlify"):
        if name in server:
            return name.title()
    return None


async def snapshot(url: str, emit=None) -> SiteSnapshot:
    """Fetch the page, its robots/sitemap/llms.txt, and probe every AI bot UA."""
    if not urlparse(url).scheme:
        url = f"https://{url}"

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, max_redirects=5) as client:
        start = time.perf_counter()
        resp = await _get(client, url, emit=emit, label="page")
        if resp is None:
            raise ValueError(f"Could not fetch {url}")
        ttfb_ms = (time.perf_counter() - start) * 1000

        origin = f"{urlparse(str(resp.url)).scheme}://{urlparse(str(resp.url)).netloc}"
        path = urlparse(str(resp.url)).path or "/"

        robots_resp, llms_resp = await asyncio.gather(
            _get(client, urljoin(origin, "/robots.txt"), emit=emit, label="robots.txt"),
            _get(client, urljoin(origin, "/llms.txt"), emit=emit, label="llms.txt"),
        )
        robots = robots_resp.text if robots_resp and robots_resp.status_code == 200 else None
        llms = llms_resp.text if llms_resp and llms_resp.status_code == 200 else None

        robots_sitemaps = [
            line.split(":", 1)[1].strip()
            for line in (robots or "").splitlines()
            if line.split("#", 1)[0].strip().lower().startswith("sitemap:")
        ]

        sitemap_candidates = robots_sitemaps or [urljoin(origin, "/sitemap.xml")]
        sitemap_resp = await _get(client, sitemap_candidates[0], emit=emit, label="sitemap.xml")
        sitemap_ok = sitemap_resp is not None and sitemap_resp.status_code == 200 and "<" in sitemap_resp.text

        browser_len = len(resp.text)
        probes = await asyncio.gather(
            *(_probe_bot(client, str(resp.url), bot, robots, path, browser_len, emit)
              for bot in sorted(PROBE_BOTS))
        )

    return SiteSnapshot(
        url=url,
        final_url=str(resp.url),
        status=resp.status_code,
        html=resp.text,
        headers={k.lower(): v for k, v in resp.headers.items()},
        ttfb_ms=ttfb_ms,
        bytes=len(resp.content),
        robots_txt=robots,
        llms_txt=llms,
        sitemap_urls=[sitemap_candidates[0]] if sitemap_ok else [],
        robots_sitemap_refs=robots_sitemaps,
        bot_probes=list(probes),
        cdn=_detect_cdn({k.lower(): v for k, v in resp.headers.items()}),
    )
