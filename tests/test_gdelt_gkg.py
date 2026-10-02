"""Tests for the GDELT GKG BigQuery net-cast (ingest/gdelt_gkg.py).

Nothing here touches real BigQuery -- GKGClient is a Protocol seam, same
purpose and shape as screening.adverse_media.MediaClient (see that module's
test file for the identical reasoning): a stub stands in so this suite stays
fast, deterministic, and off a billed cloud API.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest.gdelt_gkg import (  # noqa: E402
    GKGUnavailable,
    build_query,
    daily_flagged_persons,
    parse_person_names,
)


class StubGKGClient:
    def __init__(self, persons: list[str] | None = None, *, fail: bool = False) -> None:
        self.persons = persons if persons is not None else []
        self.fail = fail
        self.calls: list[tuple[date, str]] = []

    def fetch_persons(self, target_date: date, *, project_id: str) -> list[str]:
        self.calls.append((target_date, project_id))
        if self.fail:
            raise GKGUnavailable("stub BigQuery down")
        return self.persons


class TestParsePersonNames:
    def test_single_name_single_row(self) -> None:
        assert parse_person_names(["Vijay Mallya,120"]) == ["Vijay Mallya"]

    def test_multiple_names_one_row(self) -> None:
        # Real sample format verified live against gdelt-bq.gdeltv2.gkg_partitioned.
        names = parse_person_names(["Josef Muchitsch,172;Felber Mayr,235"])
        assert names == ["Josef Muchitsch", "Felber Mayr"]

    def test_dedupes_case_insensitively_across_rows(self) -> None:
        names = parse_person_names(["Vijay Mallya,10", "VIJAY MALLYA,99;Someone Else,5"])
        assert names == ["Vijay Mallya", "Someone Else"]

    def test_name_containing_a_comma_uses_last_comma_as_offset_boundary(self) -> None:
        # GDELT does not escape commas inside a name; the trailing segment is
        # always the numeric char offset it appended itself.
        names = parse_person_names(["Smith, Jr. John,45"])
        assert names == ["Smith, Jr. John"]

    def test_malformed_segment_without_numeric_offset_is_dropped(self) -> None:
        assert parse_person_names(["not a real segment"]) == []

    def test_empty_input(self) -> None:
        assert parse_person_names([]) == []
        assert parse_person_names([""]) == []


class TestBuildQuery:
    def test_query_bounds_are_half_open_single_day(self) -> None:
        sql = build_query(date(2026, 9, 30))
        assert "TIMESTAMP('2026-09-30')" in sql
        assert "TIMESTAMP('2026-10-01')" in sql

    def test_query_filters_on_risk_themes(self) -> None:
        sql = build_query(date(2026, 9, 30))
        assert "CORRUPTION" in sql
        assert "ECON_MONEYLAUNDERING" in sql
        assert "STARTS_WITH(theme, 'TAX_TERROR_GROUP_')" in sql

    def test_query_selects_only_persons_column(self) -> None:
        """Every extra selected column is bytes billed across the whole
        partition -- see the module docstring's live-verified cost numbers."""
        sql = build_query(date(2026, 9, 30))
        assert "SELECT DISTINCT V2Persons" in sql


class TestDailyFlaggedPersons:
    def test_returns_parsed_names_from_client(self) -> None:
        client = StubGKGClient(["Vijay Mallya,10;Ahmed Al Mansoori,50"])
        names = daily_flagged_persons(date(2026, 9, 30), project_id="test-proj", client=client)
        assert names == ["Vijay Mallya", "Ahmed Al Mansoori"]
        assert client.calls == [(date(2026, 9, 30), "test-proj")]

    def test_provider_failure_returns_empty_list_not_raise(self) -> None:
        """Soft failure, same contract as screening.adverse_media.search():
        a missed daily net-cast must not raise or block anything."""
        client = StubGKGClient(fail=True)
        names = daily_flagged_persons(date(2026, 9, 30), project_id="test-proj", client=client)
        assert names == []

    def test_no_persons_found(self) -> None:
        client = StubGKGClient([])
        assert daily_flagged_persons(date(2026, 9, 30), project_id="test-proj", client=client) == []
