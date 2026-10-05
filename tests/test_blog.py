"""Public blog, robots.txt and sitemap.xml tests."""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from amlkit.api.app import app  # noqa: E402
from amlkit.web import blog  # noqa: E402


@pytest.fixture()
def client():
    return TestClient(app)


def test_blog_index_lists_every_post(client) -> None:
    r = client.get("/blog")
    assert r.status_code == 200
    for post in blog.all_posts():
        assert f"/blog/{post.slug}" in r.text
        # Jinja escapes "&" to "&amp;" in HTML output.
        assert post.title.replace("&", "&amp;") in r.text


def test_blog_post_renders(client) -> None:
    r = client.get("/blog/uae-sanctions-screening-24-hour-rule")
    assert r.status_code == 200
    assert "24-hour freezing rule" in r.text
    assert "BlogPosting" in r.text
    assert "FAQPage" in r.text
    # Every guide cites its sources and says what it was checked against.
    assert 'id="sources"' in r.text
    assert "Checked against" in r.text


def test_blog_topic_filter(client) -> None:
    r = client.get("/blog?topic=sanctions")
    assert r.status_code == 200
    assert "/blog/uae-sanctions-screening-24-hour-rule" in r.text
    assert client.get("/blog?topic=no-such-topic").status_code == 404
    # "risk" used to have no posts; it now has the risk-assessment guide.
    risk = client.get("/blog?topic=risk")
    assert risk.status_code == 200
    assert "/blog/uae-dnfbp-aml-risk-assessment-risk-scoring" in risk.text
    assert "No guides in this topic yet" not in risk.text


def test_every_topic_now_has_at_least_one_post(client) -> None:
    # Every Topic in blog.TOPICS should resolve to a non-empty /blog?topic=
    # page -- the four non-sanctions topics started with zero posts (#376)
    # and should no longer show the "no guides yet" empty state.
    for topic, count in blog.topic_counts():
        assert count >= 1, f"topic {topic.slug!r} still has no posts"
        r = client.get(f"/blog?topic={topic.slug}")
        assert r.status_code == 200
        assert "No guides in this topic yet" not in r.text


def test_blog_search_is_server_side_without_js(client) -> None:
    hit = client.get("/blog?q=freeze")
    assert hit.status_code == 200
    assert "/blog/uae-sanctions-screening-24-hour-rule" in hit.text
    miss = client.get("/blog?q=zzzznotaword")
    assert miss.status_code == 200
    assert 'href="/blog/uae-sanctions-screening-24-hour-rule"' not in miss.text


def test_blog_search_matches_every_word() -> None:
    posts = blog.all_posts()
    assert blog.search("sanctions DNFBPs", posts)
    assert blog.search("sanctions zzzz", posts) == []


def test_related_posts_never_include_the_post_itself() -> None:
    for post in blog.all_posts():
        assert post not in blog.related_posts(post)


def test_blog_date_format() -> None:
    assert blog.format_date("2026-10-03") == "3 Oct 2026"


def test_blog_unknown_slug_is_404(client) -> None:
    r = client.get("/blog/does-not-exist")
    assert r.status_code == 404


# ---------------------------------------------------------------- new posts
# CDD/KYC, goAML reporting, risk assessment and regulatory-updates guides
# added alongside the sanctions-screening guide. Each gets the same basic
# coverage: 200, listed on /blog, no inline <script> (belt-and-suspenders
# with test_csp_no_inline_scripts.py, which scans every template), and its
# JSON-LD parses with the expected @types.

NEW_POST_SLUGS = [
    "uae-dnfbp-cdd-kyc-beneficial-ownership",
    "uae-goaml-str-sar-filing-guide",
    "uae-dnfbp-aml-risk-assessment-risk-scoring",
    "uae-aml-cft-regulatory-updates",
]


@pytest.mark.parametrize("slug", NEW_POST_SLUGS)
def test_new_post_renders_200(client, slug) -> None:
    r = client.get(f"/blog/{slug}")
    assert r.status_code == 200
    assert "BlogPosting" in r.text
    assert "FAQPage" in r.text
    assert 'id="sources"' in r.text
    assert "Checked against" in r.text


@pytest.mark.parametrize("slug", NEW_POST_SLUGS)
def test_new_post_listed_on_blog_index(client, slug) -> None:
    r = client.get("/blog")
    assert r.status_code == 200
    assert f"/blog/{slug}" in r.text
    post = blog.get_post(slug)
    assert post is not None
    assert post.title.replace("&", "&amp;") in r.text


@pytest.mark.parametrize("slug", NEW_POST_SLUGS)
def test_new_post_has_no_inline_script(client, slug) -> None:
    r = client.get(f"/blog/{slug}")
    assert r.status_code == 200
    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", r.text)
    assert inline_scripts == []


@pytest.mark.parametrize("slug", NEW_POST_SLUGS)
def test_new_post_jsonld_parses_with_expected_types(client, slug) -> None:
    r = client.get(f"/blog/{slug}")
    assert r.status_code == 200
    blocks = re.findall(r"data-jsonld='([^']*)'", r.text)
    assert blocks, f"no data-jsonld block found for {slug}"
    ld = json.loads(html.unescape(blocks[0]))
    types = {node["@type"] for node in ld["@graph"]}
    assert {"BreadcrumbList", "BlogPosting", "FAQPage"} <= types
    faq_node = next(n for n in ld["@graph"] if n["@type"] == "FAQPage")
    assert faq_node["mainEntity"], f"{slug} has no FAQ entities in its JSON-LD"
    for q in faq_node["mainEntity"]:
        assert q["@type"] == "Question"
        assert q["acceptedAnswer"]["@type"] == "Answer"


def test_new_posts_cross_reference_each_other_and_the_sanctions_guide() -> None:
    # Each new post should be reachable from at least one other post's
    # `related` field (bidirectional discovery), and should link back to
    # the existing sanctions guide rather than repeating its content.
    sanctions = blog.get_post("uae-sanctions-screening-24-hour-rule")
    assert sanctions is not None
    for slug in NEW_POST_SLUGS:
        post = blog.get_post(slug)
        assert post is not None
        related_slugs = {p.slug for p in blog.related_posts(post, limit=10)}
        assert related_slugs, f"{slug} has no related posts"


def test_robots_txt_points_at_sitemap(client) -> None:
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "Sitemap: https://groaml.grovisor.ae/sitemap.xml" in r.text


def test_sitemap_lists_public_pages_but_not_the_authenticated_home(client) -> None:
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert "<loc>https://groaml.grovisor.ae/about</loc>" in r.text
    assert "<loc>https://groaml.grovisor.ae/blog</loc>" in r.text
    for post in blog.all_posts():
        assert f"<loc>https://groaml.grovisor.ae/blog/{post.slug}</loc>" in r.text
    # "/" requires login and would just redirect a crawler -- it must not be listed.
    assert "<loc>https://groaml.grovisor.ae/</loc>" not in r.text


def test_public_header_and_footer_appear_on_content_pages_not_auth_flows(client) -> None:
    for path in ("/about", "/privacy"):
        html = client.get(path).text
        assert '<header class="no-print"' in html, path
        assert "Grovisor Business Consultants LLC. groAML" in html, path

    # Blog pages carry their own header (search, topics) and footer.
    for path in ("/blog", "/blog/uae-sanctions-screening-24-hour-rule"):
        html = client.get(path).text
        assert '<header class="bl-top no-print"' in html, path
        assert "Grovisor Business Consultants LLC. groAML" in html, path

    for path in ("/login", "/register-organization", "/setup"):
        html = client.get(path).text
        assert '<header class="no-print"' not in html, path
        assert "Grovisor Business Consultants LLC. groAML" not in html, path
