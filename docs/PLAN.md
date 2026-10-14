# SEO × GEO Dual Scanner — plan

> Saved here because `~/.claude/plans` is a symlink into iCloud Drive that macOS blocks
> this process from writing to (needs Full Disk Access for the terminal app).

## Context

The tool currently answers half the question: AI discoverability only, one score. A 2026 site owner
has two audiences that reward different things.

- **Googlebot** renders JavaScript, weighs backlinks and Core Web Vitals, ranks a list of links.
- **Answer engines** do not execute JavaScript, weigh brand mentions ~3x more than backlinks, and
  lift self-contained passages into a generated answer.

A site can be excellent for one and invisible to the other, and the gap is invisible from inside
either discipline. **That divergence is the product**, and it is also the sales pitch.

**Commercial model:** not a SaaS. A lead-generation funnel for a service. Free scan produces a
score; the score produces the pitch: "You're at 54. We'll get you to 85 in 60 days. Message us."
No billing, no tiers, no accounts.

**Sources:** `AgriciDaniel/claude-seo` (17.5k stars) and `Auriti-Labs/geo-optimizer-skill` (885),
both cloned and read in full. Every threshold is lifted from their source, not invented.

## Scoring

**SEO Score** — claude-seo's SEO Health weights:
Content 23% | Technical 22% | On-Page 20% | Schema 10% | Performance 10% | AI Readiness 10% | Images 5%

**GEO Score** — claude-seo's GEO dimensions, geo-optimizer's engine underneath:
Citability 25% (47-method engine, raw/210) | Structural 20% | Authority & Brand 20% |
Technical Access 20% | Multi-Modal 15%, then geo-optimizer's -1/-3/-5 negative penalty.

### Divergence engine

Every check declares two weights (`seo_weight`, `geo_weight`) instead of one. Divergence falls out
of the data rather than a hand-maintained list.

| Signal | SEO | GEO | Why |
|---|---|---|---|
| Client-side rendering | low | critical | Googlebot renders JS; AI crawlers do not |
| llms.txt | zero | low | Google explicitly ignores it (docs 2026-06-29) |
| FAQPage schema | zero | low | Google retired FAQ rich results for all sites May 2026 |
| Backlinks / DA | high | low | Brand mentions correlate ~3x more for AI |
| Answer-first passages | low | critical | 134-167 word blocks get lifted into answers |
| Core Web Vitals | high | low | Ranking tiebreaker; answer engines do not measure it |
| Keyword density | medium | zero | Retrieval is embedding-based |
| Google-Extended | zero | zero | Governs Gemini training, not AI Overviews eligibility |
| Top-10 position | high | high | 92% of AI Overview citations are top-10 — the one convergence |

### Promise engine

Derived, never fixed. Each failing check carries `points_recoverable` + `effort` (claude-seo's data:
robots.txt 5 min, schema ~2h/template, SSR migration 2-3 weeks), bucketed into quick wins / 30 days
/ 90 days. If the achievable ceiling is 71, the page says 71.

## Anti-hallucination guardrails

Ship as executable assertions with tests, not prose:

1. Never flag FAQPage above Info; never recommend removing it; never claim an AI-citation benefit.
2. Never recommend HowTo or the 6 other hard-deprecated schema types.
3. Never reference FID anywhere (replaced by INP 2024-03-12).
4. Never cite blocked GPTBot as evidence about ChatGPT Search citability (that is OAI-SearchBot).
   Never score Google-Extended as Google-Search readiness.
5. Never assign citation weight to llms.txt — presence only.
6. Never flag "not lazy-loaded" when a JS lazy-loader is detected.
7. Never report "no sitemap" before checking declared lines + 4 common fallbacks.
8. Never emit a backlink number with < 4 of 7 factors scoreable — literal `Not Assessed`.
9. Never treat @graph-wrapped JSON-LD as malformed — flatten first.
10. Never flag missing <priority>/<changefreq> — Google ignores them.
11. Never claim CWV thresholds tightened, or that "CWV 2.0" / "Visual Stability Index" exist.
12. Every report states scores are heuristics with no access to Google's ranking data.

Plus geo-optimizer's neutral defaults (no images -> alt 3/5; no internal links -> anchor 2/3;
short text -> boilerplate 2/4) which otherwise silently inflate results.

## Phases

**P1 (shippable)** — dual score on one page. Extend `Finding` with both weights + effort; rewrite
`score.py`; widen `fetch.py` to the 27-bot table + CDN challenge detection. ~110 deterministic
checks: port the 47 citability methods verbatim, plus on-page, schema, images, and
`content_quality.py`'s exact composite. Rebuild landing + report with `design-taste-frontend`,
findings grouped by audience: "costing you with Google" / "with AI" / "with both".

**P2** — Firecrawl site crawl (25 free / 100+ paid), which also turns the no-JS heuristic into a
real raw-vs-rendered diff; PageSpeed Insights field CWV; cross-page checks (duplicate titles,
orphans, crawl depth, hreflang mesh).

**P3** — LLM-judged checks (E-E-A-T 20/25/25/30, Who/How/Why, YMYL, intent alignment); lead funnel.
Backlinks deferred: module and 4-of-7 gate built, reporting `Not Assessed` until a key is wired.

## Verification

Guardrail tests first. Divergence fixtures: CSR marketing site -> SEO >> GEO; Markdown docs site ->
the reverse. Promise honesty: ceiling never exceeds recoverable points. Port fidelity: assert the
raw/210 denominator, spot-check ~10 methods at exact boundary values. Keep the existing 77 tests
green, especially check-order-independence.

## Risks

1. The 47-method port is the schedule risk (~3700 source lines, dozens of exact regexes). Least
   copyable part, so worth the time; honest cut is the ~20 highest-weight methods with the
   denominator adjusted.
2. Firecrawl cost is the main variable — the 25-page gate matters more than the crawler choice.
