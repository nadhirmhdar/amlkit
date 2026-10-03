"""Public blog, robots.txt and sitemap.xml tests."""

from __future__ import annotations

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
    # A real topic with no posts yet renders an empty state, not an error.
    empty = client.get("/blog?topic=risk")
    assert empty.status_code == 200
    assert "No guides in this topic yet" in empty.text


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
