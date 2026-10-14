"""Categories, weights and effort levels for the dual SEO/GEO score.

Weights are taken from the source repos rather than invented:
  SEO  - claude-seo's "SEO Health Score" category table
  GEO  - claude-seo's "GEO Readiness Score" dimension table
The GEO Citability dimension is filled by geo-optimizer's 47-method engine.
"""
from __future__ import annotations

# ---------------------------------------------------------------- SEO categories

CONTENT = "content"
TECHNICAL = "technical"
ONPAGE = "onpage"
SCHEMA = "schema"
PERFORMANCE = "performance"
AI_READINESS = "ai_readiness"
IMAGES = "images"

SEO_WEIGHTS: dict[str, float] = {
    CONTENT: 0.23,
    TECHNICAL: 0.22,
    ONPAGE: 0.20,
    SCHEMA: 0.10,
    PERFORMANCE: 0.10,
    AI_READINESS: 0.10,
    IMAGES: 0.05,
}

SEO_LABELS = {
    CONTENT: "Content quality",
    TECHNICAL: "Technical SEO",
    ONPAGE: "On-page SEO",
    SCHEMA: "Structured data",
    PERFORMANCE: "Performance",
    AI_READINESS: "AI search readiness",
    IMAGES: "Images",
}

# ---------------------------------------------------------------- GEO dimensions

CITABILITY = "citability"
STRUCTURAL = "structural"
AUTHORITY = "authority"
ACCESSIBILITY = "accessibility"
MULTIMODAL = "multimodal"

GEO_WEIGHTS: dict[str, float] = {
    CITABILITY: 0.25,
    STRUCTURAL: 0.20,
    AUTHORITY: 0.20,
    ACCESSIBILITY: 0.20,
    MULTIMODAL: 0.15,
}

GEO_LABELS = {
    CITABILITY: "Citability",
    STRUCTURAL: "Structural readability",
    AUTHORITY: "Authority & brand signals",
    ACCESSIBILITY: "Technical accessibility",
    MULTIMODAL: "Multi-modal content",
}

# ------------------------------------------------------------------- severity

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

# ---------------------------------------------------------------------- effort
# Time-to-fix, used by the promise engine. Estimates follow claude-seo's own
# figures: a robots.txt line is minutes, a schema template is hours, rewriting a
# page is days, an SSR migration is weeks.

EFFORT_MINUTES = "minutes"
EFFORT_HOURS = "hours"
EFFORT_DAYS = "days"
EFFORT_WEEKS = "weeks"

EFFORT_ORDER = [EFFORT_MINUTES, EFFORT_HOURS, EFFORT_DAYS, EFFORT_WEEKS]

# effort -> (bucket key, human timeframe, days to deliver)
EFFORT_BUCKETS: dict[str, tuple[str, str, int]] = {
    EFFORT_MINUTES: ("quick", "this week", 7),
    EFFORT_HOURS: ("quick", "this week", 7),
    EFFORT_DAYS: ("standard", "30 days", 30),
    EFFORT_WEEKS: ("heavy", "90 days", 90),
}

BUCKET_LABELS = {
    "quick": "Quick wins",
    "standard": "Standard work",
    "heavy": "Engineering work",
}

EFFORT_DESCRIPTIONS = {
    EFFORT_MINUTES: "minutes, a config or markup edit",
    EFFORT_HOURS: "hours, a template change",
    EFFORT_DAYS: "days, content or page rework",
    EFFORT_WEEKS: "weeks, an engineering project",
}


def grade(n: int) -> str:
    for threshold, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if n >= threshold:
            return letter
    return "F"


# geo-optimizer's band names, kept because they read better than letters on a
# marketing page and map to the same cut points it uses.
def band(n: int) -> str:
    if n >= 86:
        return "excellent"
    if n >= 68:
        return "good"
    if n >= 36:
        return "foundation"
    return "critical"
