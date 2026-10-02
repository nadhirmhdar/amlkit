"""Wikidata ministers/PEP adapter tests.

Offline throughout, same convention as test_ingest_cia.py: a stub httpx
transport serves canned SPARQL JSON responses for both the statement query
(phase 1) and the label-resolution query (phase 2), and parse() is exercised
against a captured-shape JSON-lines payload. Live coverage of the real
endpoint and its performance characteristics belongs in manual verification
against query.wikidata.org, not in this offline suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest.base import AdapterError  # noqa: E402
from amlkit.ingest.wikidata_peps import WikidataPEPAdapter  # noqa: E402


def _binding(**kv) -> dict:
    return {k: {"value": v} for k, v in kv.items() if v is not None}


def _sparql_response(bindings: list[dict]) -> dict:
    return {"results": {"bindings": bindings}}


def _row(person="Q1", person_label="Minister One", position="Q83307",
         position_label="Minister", country=None, country_label=None,
         start=None, end=None) -> dict:
    return {
        "person": person, "person_label": person_label,
        "position": position, "position_label": position_label,
        "country": country, "country_label": country_label,
        "start": start, "end": end,
    }


def _payload(*rows) -> bytes:
    return b"\n".join(json.dumps(r, ensure_ascii=False).encode() for r in rows)


def _parse(payload: bytes):
    return list(WikidataPEPAdapter().parse(payload))


class TestParsing:
    def test_row_becomes_pep_entity(self):
        entities = _parse(_payload(_row(country="Q1045", country_label="Belarus")))
        assert len(entities) == 1
        e = entities[0]
        assert e.caption == "Minister One"
        assert e.schema_type == "Person"
        assert e.countries == ["Belarus"]

    def test_pep_topic_is_set_and_no_sanctions_programme(self):
        e = _parse(_payload(_row()))[0]
        assert e.topics == ["role.pep"]
        assert e.programs == []

    def test_source_id_is_keyed_on_the_wikidata_qid(self):
        e = _parse(_payload(_row(person="Q42")))[0]
        assert e.source_id == "WD-Q42"
        assert ("wikidata", "Q42") in e.identifiers

    def test_missing_country_label_leaves_countries_empty(self):
        e = _parse(_payload(_row(country=None, country_label=None)))[0]
        assert e.countries == []

    def test_position_and_dates_preserved_in_raw(self):
        e = _parse(_payload(_row(position_label="Minister of Economy",
                                  start="2020-01-04T00:00:00Z", end=None)))[0]
        assert e.raw["position"] == "Minister of Economy"
        assert e.raw["start"] == "2020-01-04T00:00:00Z"
        assert e.listed_at == "2020-01-04T00:00:00Z"

    def test_blank_person_label_row_is_skipped(self):
        blank = _row(person_label="")
        blank["person"] = ""  # also blank: nothing to fall back to
        # Paired with a valid row so this exercises the per-row skip, not the
        # whole-payload "parsed 0" loud-failure guard (see the next test).
        valid = _row(person="Q7", person_label="Valid Person")
        entities = _parse(_payload(blank, valid))
        assert [e.caption for e in entities] == ["Valid Person"]

    def test_unresolved_label_falls_back_to_bare_qid(self):
        """_fetch_labels tolerates a failed batch by leaving that QID
        unresolved -- parse() must still produce a usable (if less readable)
        entity rather than silently dropping the person."""
        e = _parse(_payload(_row(person_label="", person="Q999")))[0]
        assert e.caption == "Q999"

    def test_empty_source_raises_rather_than_clearing_the_dataset(self):
        with pytest.raises(AdapterError, match="parsed 0 position-holders"):
            _parse(b"")


def test_dataset_identity_is_commercially_usable():
    adapter = WikidataPEPAdapter()
    assert adapter.is_mandatory is False  # a PEP hit does not carry a freeze duty
    assert adapter.key == "wikidata_ministers"
    assert "CC0" in adapter.licence


class _StubTransport(httpx.BaseTransport):
    """Serves phase-1 statement pages and phase-2 label batches.

    Distinguishes the two by sniffing the query text (the request is always
    a GET to the same SPARQL endpoint with a different `query` param) --
    same spirit as test_ingest_cia.py's stub distinguishing sitemap vs
    per-country requests by URL shape.
    """

    def __init__(self, pages: list[list[dict]], labels: dict[str, str]) -> None:
        self.pages = pages
        self.labels = labels
        self.statement_requests = 0
        self.label_requests = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        if "ps:P39" in query:
            idx = self.statement_requests
            self.statement_requests += 1
            page = self.pages[idx] if idx < len(self.pages) else []
            return httpx.Response(200, json=_sparql_response(page))
        if "rdfs:label" in query:
            self.label_requests += 1
            # Return a label for every QID this stub was told about, ignoring
            # exactly which ones this particular batch asked for -- adequate
            # for these tests, which only assert on the final resolved map.
            bindings = [
                _binding(id=f"http://www.wikidata.org/entity/{qid}", label=label)
                for qid, label in self.labels.items()
            ]
            return httpx.Response(200, json=_sparql_response(bindings))
        raise AssertionError(f"unexpected query shape: {query[:80]}")


@pytest.fixture
def stub(monkeypatch):
    def install(pages, labels):
        transport = _StubTransport(pages, labels)
        original = httpx.Client

        def factory(*args, **kwargs):
            kwargs["transport"] = transport
            return original(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", factory)
        return transport

    return install


class TestFetch:
    def test_single_page_fetch_and_label_resolution(self, stub):
        page = [_binding(
            person="http://www.wikidata.org/entity/Q1",
            position="http://www.wikidata.org/entity/Q83307",
        )]
        stub([page], labels={"Q1": "Someone Important", "Q83307": "Minister"})

        payload = WikidataPEPAdapter().fetch()
        rows = [json.loads(line) for line in payload.splitlines()]
        assert len(rows) == 1
        assert rows[0]["person_label"] == "Someone Important"
        assert rows[0]["position_label"] == "Minister"

    def test_pagination_stops_on_first_empty_page(self, stub):
        full_page = [
            _binding(
                person=f"http://www.wikidata.org/entity/Q{i}",
                position="http://www.wikidata.org/entity/Q83307",
            )
            for i in range(3)
        ]
        transport = stub([full_page, []], labels={"Q83307": "Minister", **{
            f"Q{i}": f"Person {i}" for i in range(3)
        }})
        payload = WikidataPEPAdapter().fetch()
        assert len(payload.splitlines()) == 3
        assert transport.statement_requests == 2  # one full page, one empty

    def test_no_rows_at_all_is_loud(self, stub):
        stub([[]], labels={})
        with pytest.raises(AdapterError, match="0 position-holder rows"):
            WikidataPEPAdapter().fetch()
