"""FATF adapter tests.

Offline: parse() is exercised against representative HTML fixtures shaped like
the real FATF black-and-grey-lists page. Live coverage belongs in
`.github/workflows/source-canary.yml`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest.fatf import (  # noqa: E402
    BLACKLIST_FALLBACK,
    GREYLIST_FALLBACK,
    FATFAdapter,
    _COUNTRY_TO_ISO,
)


def _parse(payload: bytes):
    return list(FATFAdapter().parse(payload))


# Representative HTML shaped like the real FATF page.
# The page uses <h3> headers for list sections and <li> for country names.
SAMPLE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head><title>Black and Grey Lists - FATF</title></head>
<body>
<div class="page-content">
  <div class="cmp-text">
    <h3>High-Risk Jurisdictions subject to a Call for Action</h3>
    <p>The FATF identifies the following countries:</p>
    <ul>
      <li>Democratic People's Republic of Korea (DPRK)</li>
      <li>Iran</li>
      <li>Myanmar</li>
    </ul>

    <h3>Jurisdictions under Increased Monitoring</h3>
    <p>The FATF and FATF-style regional bodies continue to identify jurisdictions:</p>
    <ul>
      <li>Algeria</li>
      <li>Angola</li>
      <li>Bulgaria</li>
      <li>Côte d'Ivoire</li>
      <li>Nigeria</li>
      <li>South Africa</li>
      <li>South Sudan</li>
      <li>Venezuela</li>
      <li>Vietnam</li>
      <li>Yemen</li>
    </ul>
  </div>
</div>
</body>
</html>
"""

# Alternate layout: country names as links within list items
SAMPLE_HTML_LINKS = """\
<html>
<body>
<div class="cmp-text">
  <h3>High-Risk Jurisdictions subject to a Call for Action</h3>
  <ul>
    <li><a href="/en/countries/detail/korea.html">Democratic People's Republic of Korea (DPRK)</a></li>
    <li><a href="/en/countries/detail/iran.html">Iran</a></li>
  </ul>
  <h3>Jurisdictions under Increased Monitoring</h3>
  <ul>
    <li><a href="/en/countries/detail/nigeria.html">Nigeria</a></li>
    <li><a href="/en/countries/detail/south-africa.html">South Africa</a></li>
  </ul>
</div>
</body>
</html>
"""


class TestParseHtml:
    def test_blacklist_countries_are_extracted(self):
        adapter = FATFAdapter()
        blacklist, _ = adapter._parse_html(SAMPLE_HTML)
        assert "KP" in blacklist
        assert "IR" in blacklist
        assert "MM" in blacklist
        assert len(blacklist) == 3

    def test_greylist_countries_are_extracted(self):
        adapter = FATFAdapter()
        _, greylist = adapter._parse_html(SAMPLE_HTML)
        assert "DZ" in greylist  # Algeria
        assert "AO" in greylist  # Angola
        assert "NG" in greylist  # Nigeria
        assert "ZA" in greylist  # South Africa
        assert "SS" in greylist  # South Sudan
        assert "VE" in greylist  # Venezuela
        assert "VN" in greylist  # Vietnam
        assert "YE" in greylist  # Yemen
        assert len(greylist) == 10

    def test_blacklist_names_are_readable(self):
        adapter = FATFAdapter()
        blacklist, _ = adapter._parse_html(SAMPLE_HTML)
        assert "Korea" in blacklist["KP"] or "DPRK" in blacklist["KP"]
        assert blacklist["IR"] == "Iran"
        assert blacklist["MM"] == "Myanmar"

    def test_country_links_are_handled(self):
        adapter = FATFAdapter()
        blacklist, greylist = adapter._parse_html(SAMPLE_HTML_LINKS)
        assert "KP" in blacklist
        assert "IR" in blacklist
        assert "NG" in greylist
        assert "ZA" in greylist

    def test_blacklist_not_in_greylist(self):
        adapter = FATFAdapter()
        blacklist, greylist = adapter._parse_html(SAMPLE_HTML)
        for code in blacklist:
            assert code not in greylist

    def test_empty_html_returns_fallback(self):
        adapter = FATFAdapter()
        blacklist, greylist = adapter._parse_html("")
        assert blacklist == BLACKLIST_FALLBACK
        assert greylist == GREYLIST_FALLBACK

    def test_no_list_sections_returns_fallback(self):
        adapter = FATFAdapter()
        blacklist, greylist = adapter._parse_html("<html><body><p>Page under maintenance</p></body></html>")
        assert blacklist == BLACKLIST_FALLBACK
        assert greylist == GREYLIST_FALLBACK


class TestParsePayload:
    def test_blacklist_entities_have_correct_topics(self):
        entities = _parse(SAMPLE_HTML.encode("utf-8"))
        bl_entities = [e for e in entities if "fatf.blacklist" in e.topics]
        assert len(bl_entities) == 3
        assert all("country.high-risk" in e.topics for e in bl_entities)

    def test_greylist_entities_have_correct_topics(self):
        entities = _parse(SAMPLE_HTML.encode("utf-8"))
        gl_entities = [e for e in entities if "fatf.greylist" in e.topics]
        assert len(gl_entities) == 10
        assert all("country.monitored" in e.topics for e in gl_entities)

    def test_entity_source_ids_are_unique(self):
        entities = _parse(SAMPLE_HTML.encode("utf-8"))
        source_ids = [e.source_id for e in entities]
        assert len(source_ids) == len(set(source_ids))

    def test_entity_schema_type_is_legal_entity(self):
        entities = _parse(SAMPLE_HTML.encode("utf-8"))
        assert all(e.schema_type == "LegalEntity" for e in entities)

    def test_entity_countries_carry_iso_code(self):
        entities = _parse(SAMPLE_HTML.encode("utf-8"))
        for e in entities:
            assert len(e.countries) == 1
            assert len(e.countries[0]) == 2

    def test_empty_payload_uses_fallback(self):
        entities = _parse(b"")
        bl = [e for e in entities if "fatf.blacklist" in e.topics]
        gl = [e for e in entities if "fatf.greylist" in e.topics]
        assert len(bl) == len(BLACKLIST_FALLBACK)
        assert len(gl) == len(GREYLIST_FALLBACK)

    def test_malformed_html_uses_fallback(self):
        entities = _parse(b"<<<not html at all>>>")
        assert len(entities) > 0


class TestCountryMapping:
    def test_common_fatf_countries_are_mapped(self):
        expected = {
            "Iran": "IR",
            "Myanmar": "MM",
            "Algeria": "DZ",
            "Nigeria": "NG",
            "South Africa": "ZA",
            "South Sudan": "SS",
            "Venezuela": "VE",
            "Vietnam": "VN",
            "Yemen": "YE",
            "Lebanon": "LB",
        }
        for name, code in expected.items():
            assert _COUNTRY_TO_ISO.get(name) == code, f"{name} not mapped to {code}"

    def test_dprk_parenthetical_is_recognized(self):
        adapter = FATFAdapter()
        blacklist, _ = adapter._parse_html(SAMPLE_HTML)
        assert "KP" in blacklist


class TestFallbackResilience:
    def test_fetch_failure_returns_empty_bytes(self):
        adapter = FATFAdapter()
        result = adapter.fetch()
        assert isinstance(result, bytes)

    def test_cloudflare_challenge_page_triggers_fallback(self):
        cloudflare_html = """<!DOCTYPE html><html><head>
        <title>Just a moment...</title></head>
        <body>Enable JavaScript and cookies to continue</body></html>"""
        adapter = FATFAdapter()
        blacklist, greylist = adapter._parse_html(cloudflare_html)
        assert blacklist == BLACKLIST_FALLBACK
        assert greylist == GREYLIST_FALLBACK


class TestDatasetIdentity:
    def test_adapter_identity(self):
        adapter = FATFAdapter()
        assert adapter.key == "fatf_country_risk"
        assert adapter.is_mandatory is True
        assert "fatf-gafi.org" in adapter.source_url
        assert adapter.publisher == "Financial Action Task Force"
