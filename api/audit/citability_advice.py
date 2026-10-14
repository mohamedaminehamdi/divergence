"""Turn weak citability methods into advisory findings with real remediation.

These carry zero scoring weight: the Citability dimension is already scored
continuously from the engine's raw/210, and counting them again would
double-penalise the same evidence. They exist to tell the user what to do.
"""
from __future__ import annotations

from .checks import Finding
from .taxonomy import EFFORT_DAYS, EFFORT_HOURS, EFFORT_MINUTES

# method name -> (human title, what to actually do, effort)
ADVICE: dict[str, tuple[str, str, str]] = {
    "answer_first": ("Open each section with a direct answer", (
        "Put a self-contained answer in the first sentence after each H2, before any context.\n"
        "Generated answers lift sentences that stand alone; one that depends on the paragraph\n"
        "above it cannot be lifted.\n\n"
        "  Weak:   ## How much does it cost?\n"
        "          We offer a range of plans designed for teams of every size...\n\n"
        "  Strong: ## How much does it cost?\n"
        "          Plans start at $29/month for Starter and $99/month for Pro."), EFFORT_DAYS),
    "answer_capsule": ("Write self-contained answer capsules", (
        "Aim for paragraphs of 30-120 words that end in a full stop, contain a concrete number,\n"
        "and do not open with 'However' or 'Moreover'. That shape is what gets quoted verbatim."), EFFORT_DAYS),
    "citability_density": ("Raise the fact density per paragraph", (
        "Target two or more citable facts per paragraph: a statistic, a named entity, a date,\n"
        "a price. Paragraphs of pure adjectives are never the source of a citation."), EFFORT_DAYS),
    "statistics_addition": ("Add concrete statistics", (
        "Replace vague claims with figures you can stand behind:\n"
        '  "significantly faster" -> "3.2x faster (180ms vs 580ms median)"\n'
        '  "trusted by many"      -> "used by 4,200 teams"'), EFFORT_DAYS),
    "chunk_quotability": ("Break content into quotable chunks", (
        "Retrievers chunk on headings. Aim for 50-150 words per section with at least one\n"
        "number in it. Long walls dilute and short stubs lose context."), EFFORT_DAYS),
    "cite_sources": ("Cite authoritative sources", (
        "Link claims to primary sources (.gov, .edu, standards bodies, papers). Citing sources\n"
        "is the same rigor signal answer engines reward when choosing whom to quote."), EFFORT_HOURS),
    "readability": ("Bring reading level into range", (
        "Target Flesch-Kincaid grade 6-8. Shorten sentences to 15-20 words and split sections\n"
        "to roughly 100-150 words between headings."), EFFORT_DAYS),
    "faq_in_content": ("Add real question-and-answer sections", (
        "Use question headings with a direct answer underneath. This is content structure, not\n"
        "FAQPage schema. Google retired FAQ rich results, but the structure still gets quoted."), EFFORT_DAYS),
    "eeat_signals": ("Strengthen trust signals", (
        "Link privacy, terms, about and contact from the page, and declare a Person author in\n"
        "schema with sameAs links to their profiles."), EFFORT_HOURS),
    "definition_patterns": ("Define your subject early", (
        'Open sections with "X is ...", "X refers to ...". Definition sentences are the single\n'
        "most-lifted sentence shape in generated answers."), EFFORT_DAYS),
    "retrieval_triggers": ("Add retrieval trigger phrases", (
        'Phrases like "according to", "research shows", "compared to", "step 1", "as of 2026"\n'
        "are what retrieval matches against. Use them where they are honest."), EFFORT_DAYS),
    "kg_density": ("State entity relationships explicitly", (
        'Write the relationships out: "X is a Y", "founded in", "developed by", "part of".\n'
        "Knowledge graphs are built from exactly these phrasings."), EFFORT_DAYS),
    "multi_platform": ("Link your profiles in sameAs", (
        "Add sameAs entries for GitHub, LinkedIn, X, YouTube, Wikipedia and Crunchbase to your\n"
        "Organization schema. Cross-platform presence is a strong AI authority signal."), EFFORT_MINUTES),
    "image_alt_quality": ("Write descriptive alt text", (
        'Alt text should describe the image in more than 10 characters and never be "image",\n'
        '"logo" or "IMG_1234". Aim for 80%+ of images descriptive.'), EFFORT_HOURS),
    "first_party_data": ("Publish original data", (
        'Original research is the most citable content there is. "We analyzed 1,200 sites and\n'
        'found..." gets cited; a summary of someone else\'s findings does not.'), EFFORT_DAYS),
    "nuance_signals": ("Acknowledge trade-offs", (
        "Add limitations, drawbacks and counterpoints. Balanced content is quoted more readily\n"
        "than uniformly positive copy, which reads as marketing."), EFFORT_DAYS),
}

MAX_ADVISORIES = 8
WEAK_RATIO = 0.6  # scoring under this share of a method's maximum counts as weak


def advisories(citability: dict) -> list[Finding]:
    """The biggest scoring gaps we can give concrete instructions for."""
    weak = [
        m for m in citability["methods"]
        if m["name"] in ADVICE and m["score"] < m["max_score"] * WEAK_RATIO
    ]
    weak.sort(key=lambda m: -(m["max_score"] - m["score"]))

    out = []
    for m in weak[:MAX_ADVISORIES]:
        title, fix, effort = ADVICE[m["name"]]
        gap = m["max_score"] - m["score"]
        out.append(Finding(
            id=f"cit_{m['name']}",
            category="citability",
            title=title,
            passed=False,
            severity="high" if gap >= 4 else "medium",
            evidence=f"Scoring {m['score']}/{m['max_score']} on citability. {m['detail']}.",
            fix=fix,
            seo_weight=0.0, geo_weight=0.0,   # already counted in the dimension score
            advisory=True,
            audience_override="ai",
            effort=effort,
            note="Citability is measured continuously, so this is advisory. It is "
                 "it is already reflected in your GEO score.",
        ))
    return out
