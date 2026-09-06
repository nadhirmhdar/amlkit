"""CIA World Leaders adapter tests.

Offline throughout: `fetch()` is exercised against a stubbed HTTP client, and
`parse()` against a captured-shape payload. Live coverage belongs in
`.github/workflows/source-canary.yml`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest.base import AdapterError  # noqa: E402
from amlkit.ingest.cia import CIAWorldLeadersAdapter  # noqa: E402


def _page(country="Algeria", code="AG", leaders=None, updated="2026-04-20 18:12:38"):
    return {
        "code": code,
        "country": country,
        "date_updated": updated,
        "leaders": leaders if leaders is not None else [
            {"name": "Abdelmadjid TEBBOUNE", "title": "Pres.", "honorific": ""},
            {"name": "Sifi GHRIEB", "title": "Prime Min.", "honorific": ""},
        ],
    }


def _payload(*pages) -> bytes:
    return b"\n".join(json.dumps(p, ensure_ascii=False).encode() for p in pages)


def _parse(payload: bytes):
    return list(CIAWorldLeadersAdapter().parse(payload))


class TestParsing:
    def test_leaders_become_pep_entities(self):
        entities = _parse(_payload(_page()))
        assert [e.caption for e in entities] == ["Abdelmadjid TEBBOUNE", "Sifi GHRIEB"]
        assert all(e.schema_type == "Person" for e in entities)

    def test_pep_topic_is_set(self):
        """queries.py and match/engine.py both classify a PEP off this topic;
        without it a world leader is stored as an unremarkable name."""
        assert _parse(_payload(_page()))[0].topics == ["role.pep"]

    def test_a_pep_carries_no_sanctions_programme(self):
        """A PEP is not designated. Emitting a programme would let pf.py file a
        head of state as a terrorism or proliferation hit."""
        entity = _parse(_payload(_page()))[0]
        assert entity.programs == []
        assert "sanction" not in entity.topics

    def test_title_and_source_are_preserved(self):
        entity = _parse(_payload(_page()))[0]
        assert entity.raw["title"] == "Pres."
        assert entity.raw["country"] == "Algeria"
        assert entity.listed_at == "2026-04-20 18:12:38"

    def test_vacant_posts_are_skipped(self):
        page = _page(leaders=[
            {"name": "Vacant", "title": "Min. of Defense", "honorific": ""},
            {"name": "", "title": "Min. of Justice", "honorific": ""},
            {"name": "Real PERSON", "title": "Pres.", "honorific": ""},
        ])
        assert [e.caption for e in _parse(_payload(page))] == ["Real PERSON"]

    def test_honorific_is_indexed_as_an_alias(self):
        page = _page(leaders=[{"name": "Someone NAMED", "title": "King", "honorific": "HRH"}])
        assert "HRH Someone NAMED" in _parse(_payload(page))[0].all_names()

    def test_namesakes_in_one_government_stay_separate(self):
        page = _page(leaders=[
            {"name": "Same NAME", "title": "Min. of Interior", "honorific": ""},
            {"name": "Same NAME", "title": "Min. of Finance", "honorific": ""},
        ])
        entities = _parse(_payload(page))
        assert len({e.source_id for e in entities}) == 2

    def test_empty_source_raises_rather_than_clearing_the_dataset(self):
        with pytest.raises(AdapterError, match="parsed 0 leaders"):
            _parse(_payload(_page(leaders=[])))


class TestCountryCodes:
    def test_fips_code_is_never_emitted_as_a_country(self):
        """The CIA publishes FIPS 10-4, not ISO 3166, and they collide: FIPS
        'AG' is Algeria while ISO 'AG' is Antigua and Barbuda. Since scorer.py
        uses this list to apply a country_mismatch PENALTY, leaking the FIPS
        code in would suppress real matches against the wrong country."""
        entity = _parse(_payload(_page(country="Algeria", code="AG")))[0]
        assert entity.countries == ["Algeria"]
        assert "AG" not in entity.countries
        assert entity.raw["fips_code"] == "AG"


class _StubTransport(httpx.BaseTransport):
    """Serves the sitemap chain and the per-country JSON documents."""

    def __init__(self, slugs, failing=()):
        self.slugs = slugs
        self.failing = set(failing)
        self.requested = []

    def handle_request(self, request):
        url = str(request.url)
        self.requested.append(url)
        if url.endswith("sitemap-index.xml"):
            body = ("<sitemapindex><sitemap><loc>"
                    "https://www.cia.gov/resources/world-leaders/sitemap/sitemap-0.xml"
                    "</loc></sitemap></sitemapindex>")
            return httpx.Response(200, text=body)
        if url.endswith("sitemap-0.xml"):
            locs = "".join(
                f"<url><loc>https://www.cia.gov/resources/world-leaders/"
                f"foreign-governments/{s}/</loc></url>"
                for s in self.slugs
            )
            # The listing page itself has the same URL shape as a country page.
            locs += ("<url><loc>https://www.cia.gov/resources/world-leaders/"
                     "foreign-governments/</loc></url>")
            return httpx.Response(200, text=f"<urlset>{locs}</urlset>")
        slug = url.split("/foreign-governments/")[1].split("/")[0]
        if slug in self.failing:
            return httpx.Response(503)
        return httpx.Response(200, json={"result": {"data": {"page": _page(country=slug)}}})


@pytest.fixture
def stub(monkeypatch):
    def install(slugs, failing=()):
        transport = _StubTransport(slugs, failing)
        original = httpx.Client

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", factory)
        return transport

    return install


class TestFetch:
    def test_every_country_in_the_sitemap_is_fetched(self, stub):
        stub([f"country-{i}" for i in range(20)])
        payload = CIAWorldLeadersAdapter().fetch()
        assert len(payload.splitlines()) == 20

    def test_the_listing_page_is_not_treated_as_a_country(self, stub):
        transport = stub(["algeria", "yemen"])
        CIAWorldLeadersAdapter().fetch()
        country_requests = [
            u for u in transport.requested if u.endswith("page-data.json")
        ]
        assert len(country_requests) == 2

    def test_a_few_country_failures_are_tolerated(self, stub):
        """A slug renamed between the sitemap build and the fetch is ordinary
        churn on a 199-page site, not a reason to lose PEP coverage."""
        slugs = [f"country-{i}" for i in range(40)]
        stub(slugs, failing=["country-7"])
        assert len(CIAWorldLeadersAdapter().fetch().splitlines()) == 39

    def test_wholesale_failure_is_loud(self, stub):
        """Ingesting a fraction of the world's leaders as though it were the
        whole list is worse than refusing: the dataset would look healthy."""
        slugs = [f"country-{i}" for i in range(20)]
        stub(slugs, failing=slugs[:10])
        with pytest.raises(AdapterError, match="refusing a partial PEP list"):
            CIAWorldLeadersAdapter().fetch()

    def test_an_empty_sitemap_is_loud(self, stub):
        stub([])
        with pytest.raises(AdapterError, match="no country pages"):
            CIAWorldLeadersAdapter().fetch()


def test_dataset_identity_is_commercially_usable():
    adapter = CIAWorldLeadersAdapter()
    assert adapter.is_mandatory is False   # a PEP hit does not carry a freeze duty
    assert adapter.key == "us_cia_world_leaders"
    assert "Public Domain" in adapter.licence
    assert "cia.gov" in adapter.source_url
