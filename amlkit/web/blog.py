"""Public blog post registry.

One entry per post; the article body lives at web/templates/blog/<slug>.html
and extends blog/_article.html for the shared layout (header, table of
contents, sources, related guides). Kept as a plain list (not a DB table)
because posts are authored and reviewed as code, same as about.html -- there
is no in-app editor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    blurb: str


# Order is the order topics are shown on /blog. A topic with no posts yet is
# still listed (with a count of 0) so readers can see what the blog covers.
TOPICS: tuple[Topic, ...] = (
    Topic("sanctions", "Sanctions & TFS",
          "Screening, the 24-hour freezing rule, and what to do on a match."),
    Topic("cdd", "CDD & KYC",
          "Customer due diligence, beneficial ownership and ongoing monitoring."),
    Topic("reporting", "goAML reporting",
          "STRs, SARs, CNMRs and PNMRs: what to file, when, and how."),
    Topic("risk", "Risk assessment",
          "Business-wide and customer risk assessment for DNFBPs."),
    Topic("regulation", "Regulatory updates",
          "Changes to UAE AML/CFT law and what they mean in practice."),
)
_TOPICS_BY_SLUG = {t.slug: t for t in TOPICS}


@dataclass(frozen=True)
class BlogPost:
    slug: str
    title: str
    description: str          # meta description and card summary (~155 chars)
    dek: str                  # the one-sentence standfirst under the headline
    published: str            # ISO date, e.g. "2026-10-03"
    updated: str
    topic: str                # a Topic.slug
    reading_minutes: int
    audience: tuple[str, ...] = ()
    featured: bool = False
    related: tuple[str, ...] = field(default=())   # other post slugs

    @property
    def topic_obj(self) -> Topic:
        return _TOPICS_BY_SLUG[self.topic]


POSTS: list[BlogPost] = [
    BlogPost(
        slug="uae-sanctions-screening-24-hour-rule",
        title="The 24-hour freezing rule: a practical guide to sanctions screening for UAE DNFBPs",
        description=(
            "Which lists trigger the 24-hour freeze, what to do in the first day after "
            "a match, how to report it on goAML, and how to build a screening process "
            "that holds up in an inspection."
        ),
        dek=(
            "When the UAE Local Terrorist List or the UN Consolidated List changes, you "
            "have hours, not days. This guide walks through exactly what a DNFBP has to "
            "do, in order, and how to prove it did."
        ),
        published="2026-10-02",
        updated="2026-10-03",
        topic="sanctions",
        reading_minutes=11,
        audience=(
            "Real estate brokers and agents",
            "Dealers in precious metals and stones",
            "Corporate service providers",
            "Auditors and accountants",
            "Lawyers and notaries",
        ),
        featured=True,
    ),
]
_BY_SLUG = {p.slug: p for p in POSTS}

for _p in POSTS:  # fail at import, not at render, if a post names a bad topic
    if _p.topic not in _TOPICS_BY_SLUG:
        raise ValueError(f"blog post {_p.slug!r} has unknown topic {_p.topic!r}")


def get_post(slug: str) -> BlogPost | None:
    return _BY_SLUG.get(slug)


def get_topic(slug: str) -> Topic | None:
    return _TOPICS_BY_SLUG.get(slug)


def all_posts() -> list[BlogPost]:
    return sorted(POSTS, key=lambda p: p.published, reverse=True)


def posts_in_topic(topic: str) -> list[BlogPost]:
    return [p for p in all_posts() if p.topic == topic]


def topic_counts() -> list[tuple[Topic, int]]:
    return [(t, len(posts_in_topic(t.slug))) for t in TOPICS]


def related_posts(post: BlogPost, limit: int = 3) -> list[BlogPost]:
    """Explicit `related` first, then same-topic posts, never the post itself."""
    picked: list[BlogPost] = []
    for slug in post.related:
        p = _BY_SLUG.get(slug)
        if p and p is not post and p not in picked:
            picked.append(p)
    for p in posts_in_topic(post.topic):
        if p is not post and p not in picked:
            picked.append(p)
    return picked[:limit]


def search(q: str, posts: list[BlogPost]) -> list[BlogPost]:
    """Case-insensitive match on every word of q against title, summary,
    topic and audience -- the same text blog.js searches client-side."""
    words = q.lower().split()
    def text(p: BlogPost) -> str:
        return " ".join((p.title, p.description, p.dek, p.topic_obj.name, *p.audience)).lower()
    return [p for p in posts if all(w in text(p) for w in words)]


def format_date(iso: str) -> str:
    """'2026-10-03' -> '3 Oct 2026' (UAE readers expect day-month order)."""
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')} {d.year}"
