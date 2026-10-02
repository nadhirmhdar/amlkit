"""Public blog post registry.

One entry per post; the template lives at web/templates/blog/<slug>.html.
Kept as a plain list (not a DB table) because posts are authored and
reviewed as code, same as about.html -- there is no in-app editor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BlogPost:
    slug: str
    title: str
    description: str
    published: str  # ISO date, e.g. "2026-10-02"
    updated: str


POSTS: list[BlogPost] = [
    BlogPost(
        slug="uae-sanctions-screening-24-hour-rule",
        title="Sanctions & PEP Screening for UAE DNFBPs: What the 24-Hour Rule Actually Requires",
        description=(
            "UAE law gives DNFBPs 24 hours to freeze funds once the Local Terrorist List "
            "or UN Consolidated List is updated. Here's what that requires in practice, "
            "and where OFAC/EU/UK screening fits beyond the legal minimum."
        ),
        published="2026-10-02",
        updated="2026-10-02",
    ),
]

_BY_SLUG = {p.slug: p for p in POSTS}


def get_post(slug: str) -> BlogPost | None:
    return _BY_SLUG.get(slug)


def all_posts() -> list[BlogPost]:
    return sorted(POSTS, key=lambda p: p.published, reverse=True)
