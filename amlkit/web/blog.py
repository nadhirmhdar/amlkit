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
        related=(
            "uae-dnfbp-cdd-kyc-beneficial-ownership",
            "uae-goaml-str-sar-filing-guide",
        ),
    ),
    BlogPost(
        slug="uae-dnfbp-cdd-kyc-beneficial-ownership",
        title="Customer due diligence for UAE DNFBPs: identity, beneficial ownership and the risk-based approach",
        description=(
            "What CDD and KYC actually require in practice: verifying identity, "
            "tracing beneficial ownership to a natural person, when a customer "
            "needs simplified, standard or enhanced due diligence, and the "
            "ongoing monitoring that doesn't stop once onboarding is done."
        ),
        dek=(
            "Sanctions screening tells you who you must refuse outright. CDD is "
            "how you decide everyone else: who they really are, who actually "
            "owns them, and how closely you need to keep watching."
        ),
        published="2026-10-04",
        updated="2026-10-04",
        topic="cdd",
        reading_minutes=11,
        audience=(
            "Real estate brokers and agents",
            "Dealers in precious metals and stones",
            "Corporate service providers",
            "Auditors and accountants",
            "Lawyers and notaries",
        ),
        related=(
            "uae-sanctions-screening-24-hour-rule",
            "uae-goaml-str-sar-filing-guide",
            "uae-dnfbp-aml-risk-assessment-risk-scoring",
        ),
    ),
    BlogPost(
        slug="uae-goaml-str-sar-filing-guide",
        title="STR and SAR filing on goAML: a practical guide for UAE DNFBPs",
        description=(
            "What goAML actually is, the real difference between an STR and an "
            "SAR, what triggers a filing obligation, realistic timelines, and "
            "the record-keeping duty that goes with every report you file."
        ),
        dek=(
            "“Without delay” is the whole rule. Here is what that means in "
            "practice, which report you file for which situation, and what "
            "a filing has to hold up to look like afterwards."
        ),
        published="2026-10-04",
        updated="2026-10-04",
        topic="reporting",
        reading_minutes=10,
        audience=(
            "Real estate brokers and agents",
            "Dealers in precious metals and stones",
            "Corporate service providers",
            "Auditors and accountants",
            "Lawyers and notaries",
        ),
        related=(
            "uae-sanctions-screening-24-hour-rule",
            "uae-dnfbp-cdd-kyc-beneficial-ownership",
            "uae-dnfbp-aml-risk-assessment-risk-scoring",
        ),
    ),
    BlogPost(
        slug="uae-dnfbp-aml-risk-assessment-risk-scoring",
        title="AML/CFT risk assessment for UAE DNFBPs: what it must cover, and why it is never finished",
        description=(
            "What a business-wide and customer risk assessment actually has to "
            "cover under Cabinet Resolution No. 134 of 2025, how risk scoring "
            "feeds the CDD tier, and why risk-scoring methodology is changing "
            "industry-wide."
        ),
        dek=(
            "A risk assessment that sits in a drawer is not a risk assessment. "
            "Here is what UAE DNFBPs have to assess, how the score becomes a "
            "due-diligence tier, and where the industry is heading next."
        ),
        published="2026-10-04",
        updated="2026-10-04",
        topic="risk",
        reading_minutes=11,
        audience=(
            "Real estate brokers and agents",
            "Dealers in precious metals and stones",
            "Corporate service providers",
            "Auditors and accountants",
            "Lawyers and notaries",
        ),
        related=(
            "uae-dnfbp-cdd-kyc-beneficial-ownership",
            "uae-sanctions-screening-24-hour-rule",
            "uae-goaml-str-sar-filing-guide",
        ),
    ),
    BlogPost(
        slug="uae-aml-cft-regulatory-updates",
        title="UAE AML/CFT regulatory updates: what changed, and what DNFBPs need to do",
        description=(
            "A running guide to the current UAE AML/CFT legal framework: "
            "Federal Decree-Law No. 10 of 2025, its Executive Regulations, and "
            "what's followed since, kept current rather than written once."
        ),
        dek=(
            "The law changed in October 2025 and the rulebook that implements "
            "it changed again in December. Here is what actually moved, what "
            "is still settling, and what to check before you rely on any of it."
        ),
        published="2026-10-04",
        updated="2026-10-04",
        topic="regulation",
        reading_minutes=9,
        audience=(
            "Real estate brokers and agents",
            "Dealers in precious metals and stones",
            "Corporate service providers",
            "Auditors and accountants",
            "Lawyers and notaries",
        ),
        related=(
            "uae-sanctions-screening-24-hour-rule",
            "uae-dnfbp-cdd-kyc-beneficial-ownership",
            "uae-goaml-str-sar-filing-guide",
            "uae-dnfbp-aml-risk-assessment-risk-scoring",
        ),
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
