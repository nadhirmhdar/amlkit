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
from amlkit.ingest.wikidata_peps import WikidataPEPAdapter, _statement_query  # noqa: E402


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
        assert e.raw["positions"] == [{
            "position": "Minister of Economy", "position_qid": "Q83307",
            "country": None, "start": "2020-01-04T00:00:00Z", "end": None,
        }]
        assert e.listed_at == "2020-01-04T00:00:00Z"

    def test_person_holding_two_positions_yields_one_entity_not_two(self):
        """Regression test: parse() used to yield one entity per
        (person, position) row, all sharing the same source_id (keyed on
        the person QID alone) -- entities.(dataset_id, source_id) is
        UNIQUE, so a person with two posts crashed load() with a bare
        sqlite3.IntegrityError that none of this adapter's callers catch.
        One entity per person, with every position collected into
        raw["positions"], fixes this."""
        first = _row(person="Q7", person_label="Multi Minister",
                     position="Q1", position_label="Minister of Finance",
                     start="2018-06-01T00:00:00Z")
        second = _row(person="Q7", person_label="Multi Minister",
                      position="Q2", position_label="Deputy Prime Minister",
                      start="2020-01-01T00:00:00Z")
        entities = _parse(_payload(first, second))
        assert len(entities) == 1
        e = entities[0]
        assert e.source_id == "WD-Q7"
        assert len(e.raw["positions"]) == 2
        assert {p["position"] for p in e.raw["positions"]} == {
            "Minister of Finance", "Deputy Prime Minister",
        }
        # Earliest of the two starts, not the second row's.
        assert e.listed_at == "2018-06-01T00:00:00Z"

    def test_two_positions_merge_country_labels_without_duplicates(self):
        first = _row(person="Q7", person_label="Multi Minister",
                     country="Q1045", country_label="Belarus")
        second = _row(person="Q7", person_label="Multi Minister",
                      country="Q1045", country_label="Belarus")
        third = _row(person="Q7", person_label="Multi Minister",
                     country="Q159", country_label="Russia")
        e = _parse(_payload(first, second, third))[0]
        assert e.countries == ["Belarus", "Russia"]

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


class TestKeysetQuery:
    """Regression tests for the OFFSET -> keyset pagination fix. Plain
    OFFSET with no stable ORDER BY was measured live to return only ~21%
    overlap between two otherwise-identical paginated calls -- rows were
    silently skipped or duplicated across page boundaries, and the loader
    deletes entities missing from a refresh (cascading to their alerts),
    so a PEP could lose its alert history just from unlucky pagination."""

    def test_first_page_has_no_keyset_filter(self):
        query = _statement_query(2000, None)
        assert "FILTER(STR(?person) >" not in query
        assert "ORDER BY STR(?person)" in query
        assert "OFFSET" not in query

    def test_later_page_filters_on_the_previous_boundary(self):
        query = _statement_query(2000, "http://www.wikidata.org/entity/Q108443110")
        assert 'FILTER(STR(?person) > "http://www.wikidata.org/entity/Q108443110")' in query
        assert "ORDER BY STR(?person)" in query

    def test_order_by_and_filter_use_the_same_cast(self):
        """ORDER BY ?person (the raw IRI term) and a STR(?person) filter
        sort/compare differently -- live-verified: ordering by the IRI
        term took ~29s and produced a different order than ordering by its
        string form (~6s), so mixing the two cast styles would compare
        pages sorted one way against a boundary computed the other way."""
        query = _statement_query(2000, "http://www.wikidata.org/entity/Q1")
        assert "ORDER BY STR(?person)" in query
        assert "ORDER BY ?person\n" not in query
        assert "ORDER BY ?person " not in query

    def test_boundary_value_is_escaped(self):
        """The boundary flows from a previous HTTP response's JSON back
        into the next request's query text -- escaped defensively even
        though a real Wikidata IRI will never contain a quote."""
        query = _statement_query(2000, 'http://example/Q1"); DROP')
        assert '\\"' in query


class TestKeysetFetchIntegration:
    def test_second_page_request_carries_first_pages_last_person(self, stub):
        """_fetch_statements must compute the next page's keyset boundary
        from the ACTUAL last row of the previous page, not from some other
        value -- otherwise pages can silently gap or overlap exactly the
        way plain OFFSET did."""
        page1 = [
            _binding(person="http://www.wikidata.org/entity/Q1", position="http://www.wikidata.org/entity/Q83307"),
            _binding(person="http://www.wikidata.org/entity/Q5", position="http://www.wikidata.org/entity/Q83307"),
        ]
        transport = stub([page1, []], labels={"Q1": "A", "Q5": "B", "Q83307": "Minister"})

        queries = []
        real_handle = transport.handle_request

        def recording_handle(request):
            queries.append(request.url.params.get("query", ""))
            return real_handle(request)

        transport.handle_request = recording_handle

        WikidataPEPAdapter().fetch()

        statement_queries = [q for q in queries if "ps:P39" in q]
        assert len(statement_queries) == 2
        assert "FILTER(STR(?person) >" not in statement_queries[0]
        assert 'FILTER(STR(?person) > "http://www.wikidata.org/entity/Q5")' in statement_queries[1]


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

    def test_transient_statement_failure_is_retried_not_fatal(self, stub, monkeypatch):
        """The module docstring itself says this endpoint "reliably times
        out" under load across ~95-120 sequential calls -- a single
        transient failure must be retried, not abort the whole run."""
        import time
        monkeypatch.setattr(time, "sleep", lambda *_: None)

        page = [_binding(
            person="http://www.wikidata.org/entity/Q1",
            position="http://www.wikidata.org/entity/Q83307",
        )]
        transport = stub([page], labels={"Q1": "Someone Important", "Q83307": "Minister"})

        real_handle = transport.handle_request
        calls = {"n": 0}

        def flaky_handle(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503, text="temporarily unavailable")
            return real_handle(request)

        transport.handle_request = flaky_handle

        payload = WikidataPEPAdapter().fetch()
        rows = [json.loads(line) for line in payload.splitlines()]
        assert len(rows) == 1
        assert calls["n"] >= 2  # first call failed, a retry actually happened

    def test_statement_failure_exhausting_retries_raises_adapter_error(self, stub, monkeypatch):
        import time
        monkeypatch.setattr(time, "sleep", lambda *_: None)

        transport = stub([[]], labels={})
        transport.handle_request = lambda request: httpx.Response(503, text="still down")

        with pytest.raises(AdapterError, match="statement query failed"):
            WikidataPEPAdapter().fetch()


class TestRobotPolicyBlock:
    def test_403_fails_fast_without_retrying_and_says_why(self, stub, monkeypatch):
        """Wikimedia answers a blocked IP with 403 'Please respect our robot
        policy'. Retrying adds to the traffic that caused it, so the adapter
        must stop at once and name the cause."""
        import time
        monkeypatch.setattr(time, "sleep", lambda *_: pytest.fail("must not back off and retry a 403"))

        transport = stub([[]], labels={})
        calls = {"n": 0}

        def blocked(request):
            calls["n"] += 1
            return httpx.Response(403, text="Please respect our robot policy https://w.wiki/4wJS")

        transport.handle_request = blocked
        with pytest.raises(AdapterError, match="robot policy") as exc:
            WikidataPEPAdapter().fetch()
        assert calls["n"] == 1
        assert "bot-traffic@wikimedia.org" in str(exc.value)

    def test_user_agent_names_the_product_and_a_contact(self):
        from amlkit.ingest import wikidata_peps as w
        assert "groAML" in w.USER_AGENT and ("@" in w.USER_AGENT or "http" in w.USER_AGENT)
