# Contributing

## Setup

Two services, run independently.

```bash
# API  (http://localhost:8077)  - Python 3.12+, uv
cd api
cp .env.example .env            # every value is optional
uv run uvicorn main:app --port 8077 --reload

# Web  (http://localhost:3000)  - Node 20+
cd web
echo 'NEXT_PUBLIC_API_URL=http://localhost:8077' > .env.local
npm install && npm run dev
```

Neither needs credentials to start. Without `DATABASE_URL` the API keeps scans in memory; without
engine API keys the deterministic audit still runs in full and the live visibility scan is disabled.

## Tests

```bash
cd api && uv run pytest         # 188 tests, no network, no API calls
cd web && npx tsc --noEmit      # type check
cd web && npx next build        # must succeed before a PR
```

The Python suite must stay offline. Engine clients are tested against recorded responses; a test
that makes a real HTTP call will be rejected.

## Adding a check

A check is a function returning a `Finding`. The runner maps over a registry, so adding one means
appending a function, not touching the pipeline.

1. Write it in `api/audit/seo_checks.py` (search side) or alongside the citability engine.
2. Declare **both** weights in `api/audit/weights.py`. Every check carries a `seo_weight` and a
   `geo_weight`; a zero on either side is a claim and needs a source comment saying why.
3. Attach a fix, or mark the finding advisory. Advisory findings must not carry scoring weight;
   a guardrail enforces this.
4. Add a test. If the check can fire incorrectly in a way that would mislead a user, add a
   guardrail in `api/audit/guardrails.py` and a test proving it fires.

## Guardrails

`api/audit/guardrails.py` holds executable assertions over the finished report. They exist because
the underlying sources encode constraints that auditors routinely get wrong, and because a scoring
bug that silently produces a plausible number is worse than a crash.

```bash
cd api && uv run pytest tests/test_guardrails.py
```

If you add a recommendation the tool can make, consider whether it can ever be wrong in a way the
user cannot detect. If so, it needs a guardrail.

## Frontend conventions

- Tailwind v4. Custom classes live in `@layer components` in `app/globals.css` so utilities win.
- One radius system: interactive elements are pills, containers are 22px panels.
- Three surface tiers, used by hierarchy, not by taste: `.glass-hi` forward, `.glass` base,
  `.glass-deep` receding.
- The two audiences are distinguished by weight, never by hue. Search is dimmed white, AI is full
  white. Do not introduce a colour accent.
- Minimum font size is 11px. Uppercase tracked labels are rationed; do not add one above every
  section heading.
- Anything animated needs a `prefers-reduced-motion` path, and anything translucent needs a
  `prefers-reduced-transparency` fallback.

## Secrets

Never commit real credentials. `api/.env.example` is the template and carries empty values.
`.env` and `.env.*` are gitignored; `.env.example` is the only exception. All keys are read from
the environment at call time, never stored in source.

## Commits

Present tense, imperative, explaining why rather than what. Keep unrelated changes in separate
commits.
