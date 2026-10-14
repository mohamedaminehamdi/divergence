"""Copy-paste remediation snippets, filled in with the site's own values.

The score is a toy without these. Every failed check must hand back something
the user can paste somewhere.
"""
from __future__ import annotations

import json

ROBOTS_ALLOW_BLOCK = """\
# Allow AI answer engines to read this site
User-agent: GPTBot
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Claude-SearchBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

Sitemap: {origin}/sitemap.xml
"""


def robots_allow(origin: str, bots: list[str] | None = None) -> str:
    if not bots:
        return ROBOTS_ALLOW_BLOCK.format(origin=origin)
    blocks = "\n\n".join(f"User-agent: {b}\nAllow: /" for b in bots)
    return f"# Add to robots.txt. Currently blocking these\n{blocks}\n"


def llms_txt(brand: str, origin: str, description: str, pages: list[tuple[str, str]]) -> str:
    """llms.txt is a plain markdown index of what matters on the site."""
    lines = [f"# {brand}", "", f"> {description or 'Add a one-line description of what this site offers.'}", ""]
    if pages:
        lines += ["## Key pages", ""]
        lines += [f"- [{title}]({url}): what this page covers" for title, url in pages[:10]]
    else:
        lines += [
            "## Key pages",
            "",
            f"- [Docs]({origin}/docs): product documentation",
            f"- [Pricing]({origin}/pricing): plans and pricing",
            f"- [About]({origin}/about): who we are",
        ]
    lines += ["", "## Optional", "", f"- [Changelog]({origin}/changelog): release history"]
    return "\n".join(lines) + "\n"


def organization_jsonld(brand: str, origin: str, description: str) -> str:
    return _script(
        {
            "@context": "https://schema.org",
            "@type": "Organization",
            "name": brand,
            "url": origin,
            "description": description or f"What {brand} does, in one sentence.",
            "logo": f"{origin}/logo.png",
            "sameAs": [
                "https://www.linkedin.com/company/YOUR-COMPANY",
                "https://x.com/YOUR-HANDLE",
                "https://github.com/YOUR-ORG",
                "https://en.wikipedia.org/wiki/YOUR-ENTITY",
            ],
        }
    )


def article_jsonld(title: str, url: str, brand: str) -> str:
    return _script(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "url": url,
            "datePublished": "2026-01-15",
            "dateModified": "2026-09-21",
            "author": {"@type": "Person", "name": "Author Name", "url": f"{url.rstrip('/')}/../about/author"},
            "publisher": {"@type": "Organization", "name": brand},
        }
    )


def qa_jsonld(questions: list[str]) -> str:
    """QAPage, not FAQPage.

    Google retired FAQ rich results for all sites in May 2026. FAQPage markup is
    not harmful and existing markup should be left alone, but recommending new
    FAQPage markup sends people to build something that produces nothing. QAPage
    is the live type for genuine user question-and-answer content.
    """
    qs = questions[:3] or ["What is X?", "How much does X cost?"]
    return _script(
        {
            "@context": "https://schema.org",
            "@type": "QAPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": q,
                    "acceptedAnswer": {"@type": "Answer", "text": "A direct, self-contained answer in 2-3 sentences."},
                }
                for q in qs
            ],
        }
    )


def _script(obj: dict) -> str:
    return '<script type="application/ld+json">\n' + json.dumps(obj, indent=2) + "\n</script>"
