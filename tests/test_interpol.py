"""Tests for Interpol Red Notices ingest adapter."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest.base import AdapterError


PAGE_1 = {
    "total": 3,
    "_embedded": {
        "notices": [
            {
                "entity_id": "2021-12345",
                "forename": "MALLYA",
                "name": "Test",
                "date_of_birth": "1955/10/18",
                "nationalities": ["IN"],
                "arrest_warrants": [
                    {"issuing_country_id": "IN", "charge": "Money laundering"}
                ],
                "_links": {"self": {"href": "/notices/v1/red/2021-12345"}},
            },
            {
                "entity_id": "2020-99999",
                "forename": "Ahmed",
                "name": "Al Fugitive",
                "date_of_birth": "1980/03/22",
                "nationalities": ["AE", "LB"],
                "arrest_warrants": [
                    {"issuing_country_id": "AE", "charge": "Fraud"},
                    {"issuing_country_id": "LB", "charge": "Embezzlement"},
                ],
                "_links": {"self": {"href": "/notices/v1/red/2020-99999"}},
            },
        ],
    },
    "_links": {
        "self": {"href": "/notices/v1/red?page=1&resultPerPage=160"},
        "next": {"href": "/notices/v1/red?page=2&resultPerPage=160"},
    },
}

PAGE_2 = {
    "total": 3,
    "_embedded": {
        "notices": [
            {
                "entity_id": "2019-55555",
                "forename": "Maria",
                "name": "Gonzalez",
                "date_of_birth": "1970/06/15",
                "nationalities": ["MX"],
                "arrest_warrants": [
                    {"issuing_country_id": "MX", "charge": "Drug trafficking"}
                ],
                "_links": {"self": {"href": "/notices/v1/red/2019-55555"}},
            },
        ],
    },
    "_links": {
        "self": {"href": "/notices/v1/red?page=2&resultPerPage=160"},
    },
}


def _mock_get(url, **kwargs):
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    if "page=2" in url:
        resp.json.return_value = PAGE_2
        resp.content = json.dumps(PAGE_2).encode()
    else:
        resp.json.return_value = PAGE_1
        resp.content = json.dumps(PAGE_1).encode()
    return resp


class TestInterpolAdapter:
    def test_fetches_and_parses_two_pages(self) -> None:
        from amlkit.ingest.interpol import InterpolRedNoticeAdapter

        adapter = InterpolRedNoticeAdapter()
        assert adapter.key == "interpol_red_notices"
        assert adapter.is_mandatory is False

        with patch("httpx.get", side_effect=_mock_get):
            payload = adapter.fetch()
            entities = list(adapter.parse(payload))

        assert len(entities) == 3

    def test_known_fugitive_has_correct_fields(self) -> None:
        from amlkit.ingest.interpol import InterpolRedNoticeAdapter

        adapter = InterpolRedNoticeAdapter()
        with patch("httpx.get", side_effect=_mock_get):
            payload = adapter.fetch()
            entities = list(adapter.parse(payload))

        mallya = next(e for e in entities if "MALLYA" in e.caption)
        assert mallya.source_id == "interpol/2021-12345"
        assert mallya.schema_type == "Person"
        assert mallya.caption == "MALLYA Test"
        assert set(mallya.topics) == {"crime", "fugitive", "red-notice"}
        assert "IN" in mallya.programs
        assert mallya.birth_date == "1955-10-18"
        assert "IN" in mallya.countries

    def test_multiple_nationalities_preserved(self) -> None:
        from amlkit.ingest.interpol import InterpolRedNoticeAdapter

        adapter = InterpolRedNoticeAdapter()
        with patch("httpx.get", side_effect=_mock_get):
            payload = adapter.fetch()
            entities = list(adapter.parse(payload))

        ahmed = next(e for e in entities if "Ahmed" in e.caption)
        assert "AE" in ahmed.countries
        assert "LB" in ahmed.countries

    def test_multiple_warrant_countries_in_programs(self) -> None:
        from amlkit.ingest.interpol import InterpolRedNoticeAdapter

        adapter = InterpolRedNoticeAdapter()
        with patch("httpx.get", side_effect=_mock_get):
            payload = adapter.fetch()
            entities = list(adapter.parse(payload))

        ahmed = next(e for e in entities if "Ahmed" in e.caption)
        assert "AE" in ahmed.programs
        assert "LB" in ahmed.programs

    def test_empty_response_raises_adapter_error(self) -> None:
        from amlkit.ingest.interpol import InterpolRedNoticeAdapter

        def mock_empty(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"_embedded": {"notices": []}, "_links": {}}
            resp.content = b'{"_embedded":{"notices":[]},"_links":{}}'
            return resp

        adapter = InterpolRedNoticeAdapter()
        with patch("httpx.get", side_effect=mock_empty):
            payload = adapter.fetch()
            with pytest.raises(AdapterError):
                list(adapter.parse(payload))
