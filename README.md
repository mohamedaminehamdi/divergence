# SEO × GEO Scanner

Scores a page twice — once for search crawlers, once for answer engines — and shows the gap between
them.

Google and ChatGPT reward different things. Googlebot renders JavaScript, weighs backlinks and Core
Web Vitals, and ranks a list of links. Answer engines never execute JavaScript, weigh brand mentions
roughly 3× over backlinks, and lift one self-contained passage into a generated answer. A site can
be strong for one and invisible to the other, and no single-score audit will tell you which.

**That divergence is the product**, and it is also the pitch: the free scan produces two scores,
the gap between them, and a count of what is holding the page back, then books a call. No billing,
no tiers, no accounts.

The report names what is wrong and shows the evidence. The remediation detail is the paid
engagement and is deliberately not rendered in the public report.

## Live demo

**https://mohamedaminehamdi.github.io/divergence/**

The demo is the web app built as static files and served from GitHub Pages. GitHub
Pages hosts files only, so the Python API is not running behind it, and the scanner
says so instead of scanning. To make the hosted copy scan for real, deploy `api/`
somewhere that runs Python, then set the repository variable `API_URL` to its address
(Settings → Secrets and variables → Actions → Variables) and add the Pages origin to
the API's `CORS_ORIGINS`.

Every push to `main` redeploys it through `.github/workflows/pages.yml`.

## Run it

```bash
# API  (http://localhost:8077)
cd api
uv run uvicorn main:app --port 8077 --reload

# Web  (http://localhost:3000)
cd web
echo 'NEXT_PUBLIC_API_URL=http://localhost:8077' > .env.local
npm install && npm run dev
```

Nothing is required to start. Without `DATABASE_URL` the API keeps scans in memory; without engine
API keys the deterministic audit still runs in full.

## Test

```bash
cd api && uv run pytest        # 188 tests, no network, no API calls
```

## Scoring

Two independent 0–100 scores, using weights taken from the source repos rather than invented.

**Search** — `claude-seo`'s SEO Health Score weights:

| Category | Weight |
|---|---|
| Content quality | 23% |
| Technical SEO | 22% |
| On-page SEO | 20% |
| Structured data | 10% |
| Performance | 10% |
| AI search readiness | 10% |
| Images | 5% |

**AI visibility** - `claude-seo`'s GEO Readiness dimensions, with `geo-optimizer`'s engine underneath:

| Dimension | Weight | Source |
|---|---|---|
| Citability | 25% | the 47-method engine, scored continuously as raw/210 |
| Structural readability | 20% | heading hierarchy, question headings, chunk size |
| Authority & brand signals | 20% | entity schema, byline, dates, sameAs |
| Technical accessibility | 20% | per-bot robots.txt, CDN blocks, no-JS content |
| Multi-modal content | 15% | media mix, alt coverage, transcripts |

### The divergence engine

Every check declares **two** weights — `seo_weight` and `geo_weight` — in
[`audit/weights.py`](api/audit/weights.py). The contrast view is generated from the gaps between
them, so it stays correct as checks are added rather than drifting from a hand-maintained list.

Several zero weights are load-bearing and sourced:

- `llms.txt` has **zero** search weight — Google states it ignores the file.
- `FAQPage` has zero search weight — Google retired FAQ rich results for all sites.
- Training-only crawler tokens (`GPTBot`, `ClaudeBot`, `Google-Extended`) score **zero on both
  sides**. Blocking GPTBot does not affect whether ChatGPT can *cite* you — that is `OAI-SearchBot`.

### Asymmetric caps

Caps apply per side, because the failure modes are not symmetric:

- Every citation crawler disallowed → **AI capped at 40**
- Googlebot disallowed → **search capped at 40**
- No content without JavaScript → **AI capped at 50**, search untouched (Googlebot renders JS)

### The promise

Computed, never asserted. For each effort bucket the failing findings are marked passed and the real
scorer is re-run, so the projected number is exactly what the audit would return after that work.
Findings with no fix attached are excluded. If the ceiling is 71, the page says 71.

## Guardrails

Both source repos encode constraints that auditors routinely get wrong. They ship as executable
assertions over the finished report ([`audit/guardrails.py`](api/audit/guardrails.py)), each with a
test proving it fires — never reference FID, never recommend deprecated schema, never raise
`FAQPage` above Info, never claim a training-only bot affects citability, never emit a backlink
number below 4 of 7 factors, never let an advisory carry scoring weight.

```bash
cd api && uv run pytest tests/test_guardrails.py
```

Verified clean against six live sites.

## Layout

```text
api/
  audit/bots.py            27 crawlers, 3 tiers, citation vs training
  audit/checks.py          Finding + the base check registry
  audit/seo_checks.py      classic SEO: on-page, technical, images, content
  audit/citability.py      the 47-method engine (raw/210)
  audit/citability_advice.py  weak methods -> advisory findings with fixes
  audit/weights.py         the divergence table          <- the thesis
  audit/score.py           dual scorer + asymmetric caps
  audit/promise.py         simulated uplift by effort bucket
  audit/guardrails.py      executable anti-hallucination rules
  visibility/              live brand-citation scan across 4 engines
web/
  app/page.tsx             landing
  app/r/ReportView.tsx     shareable report at /r?id=..., loaded in the browser
  app/components/ParticleSphere.tsx  the WebGL sphere behind the landing page
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, the test contract, and how to add a check.

## Sources

Checks and thresholds are ported from two open-source repos rather than re-derived:

- [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) — score weights, on-page and
  technical thresholds, content-quality formula, the "do not do this" rules
- [Auriti-Labs/geo-optimizer-skill](https://github.com/Auriti-Labs/geo-optimizer-skill) — the
  47-method citability engine, crawler taxonomy, negative-signal ladder

## Status

Phase 1 complete: dual scoring on a single page, divergence, promise, guardrails, UI.

Not yet built: site-wide crawl via Firecrawl, PageSpeed Insights for real Core Web Vitals field
data, LLM-judged checks (E-E-A-T, YMYL, intent alignment), and backlinks. The backlink module's
4-of-7 data-sufficiency gate is specified and guarded but reports `Not Assessed` until a provider
key is wired.

**Known limitation:** the *search* ceiling currently reaches 100 on most pages, because every
search-side check is binary and therefore fixable by toggling. The AI ceiling is already realistic
(82–90) because citability is scored continuously. Adding PageSpeed Insights in phase 2 fixes this —
field Core Web Vitals are measured, not toggled. Until then the UI labels it "ceiling if every fix
lands" rather than a prediction.

## License

[PolyForm Noncommercial 1.0.0](LICENSE). You may read, run, modify and share this
code for any **noncommercial** purpose, including personal use, research, education,
and use by charities and public bodies. Commercial use is not permitted.

This makes the project *source-available* rather than open source in the strict sense:
the Open Source Definition requires allowing commercial use, which this license does
not. For commercial licensing, contact the author.

