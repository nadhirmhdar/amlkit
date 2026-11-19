"""Customers hold ISO codes, most reference lists hold English names.

Regression: an exact-name PEP hit (India's Home Minister) was dropped for an
Indian customer because "IN" != "India" was read as a country mismatch (-0.20,
1.0 -> 0.80, under the 0.85 alert threshold).
"""
import pytest

from amlkit.countries import to_alpha2
from amlkit.datamodel import COUNTRY_CODES
from amlkit.ingest.wikidata_peps import WikidataPEPAdapter
from amlkit.match.scorer import P_COUNTRY_MISMATCH, score_entity


@pytest.mark.parametrize("value, code", [
    ("IN", "IN"), ("in", "IN"), ("India", "IN"), (" india ", "IN"),
    ("Russia", "RU"), ("Russian Federation", "RU"),
    ("Korea, North", "KP"), ("Korea, Democratic People's Republic of", "KP"),
    ("Burma", "MM"), ("Myanmar", "MM"), ("Cote d'Ivoire", "CI"), ("Côte d’Ivoire", "CI"),
    ("Iran, Islamic Republic of", "IR"), ("United States of America", "US"),
    ("Syrian Arab Republic", "SY"), ("Türkiye", "TR"), ("Viet Nam", "VN"),
])
def test_resolves_codes_and_names(value, code):
    assert to_alpha2(value) == code


@pytest.mark.parametrize("value", [None, "", "  ", "Narnia", "ZZ", "Europe"])
def test_unknown_is_none_not_a_country(value):
    assert to_alpha2(value) is None


def test_every_supported_country_code_resolves_by_name():
    from amlkit.countries import _TABLE
    assert COUNTRY_CODES <= set(_TABLE), sorted(COUNTRY_CODES - set(_TABLE))
    for code in _TABLE:
        assert to_alpha2(_TABLE[code].split("|")[0]) == code


def _adj(query, cand):
    r = score_entity("Amit Shah", ["Amit Shah"], query_countries=query, cand_countries=cand)
    return r.score, r.features.get("adjustments", {})


@pytest.mark.parametrize("query", [["IN"], ["in"], ["IN", "AE"], ["AE", "IN"], ["India"]])
def test_code_vs_name_same_country_is_not_a_mismatch(query):
    score, adj = _adj(query, ["India"])
    assert "country_mismatch" not in adj
    assert score == pytest.approx(1.0)


def test_different_countries_still_penalised():
    score, adj = _adj(["AE"], ["India"])
    assert adj == {"country_mismatch": P_COUNTRY_MISMATCH}
    assert score == pytest.approx(1.0 + P_COUNTRY_MISMATCH)


def test_two_names_for_the_same_country_agree():
    _, adj = _adj(["Russian Federation"], ["Russia"])
    assert "country_mismatch" not in adj


def test_unresolvable_country_is_never_a_mismatch():
    # We cannot tell, so we must not count it against the match.
    for query, cand in ((["IN"], ["Atlantis"]), (["Atlantis"], ["India"])):
        _, adj = _adj(query, cand)
        assert "country_mismatch" not in adj


def test_one_unresolved_candidate_country_withholds_penalty():
    _, adj = _adj(["AE"], ["India", "Atlantis"])
    assert "country_mismatch" not in adj


def test_indian_customer_alerts_on_pep_snapshot_entry(tmp_path):
    """End to end on a real DB: Amit Shah as an Indian (or UAE-resident Indian) customer."""
    import gzip
    import json

    from amlkit.db import connect
    from amlkit.ingest import loader
    from amlkit.match.engine import DEFAULT_THRESHOLD, screen

    rows = [{"person": "Q4746875", "person_label": "Amit Shah", "position": "Q3440901",
             "position_label": "Minister of Home Affairs", "country": "Q668",
             "country_label": "India", "start": "2019-05-30T00:00:00Z", "end": None}]
    payload = "\n".join(json.dumps(r) for r in rows).encode()
    conn = connect(str(tmp_path / "t.db"))
    loader.load(conn, _Fixed(payload))
    for kw in ({}, {"country": "IN"}, {"countries": ["IN", "AE"]}):
        res = screen(conn, "Amit Shah", org_id=1, persist=False, **kw)
        assert res.hits and res.hits[0].score >= DEFAULT_THRESHOLD, kw
        assert "role.pep" in res.hits[0].topics


class _Fixed(WikidataPEPAdapter):
    def __init__(self, payload):
        super().__init__()
        self._payload = payload

    def fetch(self):
        return self._payload


# ------------------------------------------------- DOB near-miss (S4 residual)
from amlkit.match.scorer import P_DOB_DAY_MISMATCH, P_DOB_NEAR_MISS  # noqa: E402


def _dob(query, cand):
    r = score_entity("Bilal Ali Al Wafi", ["Bilal Ali Al Wafi"],
                     query_birth_date=query, cand_birth_date=cand)
    return r.score, r.features.get("adjustments", {})


@pytest.mark.parametrize("query, cand", [
    ("1975-03-13", "1975-03-12"),   # off by a day
    ("1975-03-31", "1975-03-01"),   # typo in the day
    ("1975-12-03", "1975-03-12"),   # day/month swapped
])
def test_dob_typo_or_dd_mm_swap_still_alerts_on_exact_name(query, cand):
    score, adj = _dob(query, cand)
    assert adj == {"dob_near_miss": P_DOB_NEAR_MISS}
    assert score >= 0.85


@pytest.mark.parametrize("query, cand", [
    ("1975-09-09", "1975-03-12"),   # same year, different month and day
    ("1975-03-12", "1975-11-12"),   # same day, different month
])
def test_dob_with_a_real_contradiction_keeps_the_full_penalty(query, cand):
    score, adj = _dob(query, cand)
    assert adj == {"dob_day_mismatch": P_DOB_DAY_MISMATCH}
    assert score < 0.85


def test_dob_different_year_unchanged_and_exact_dob_unpenalised():
    assert "dob_year_mismatch" in _dob("1976-03-12", "1975-03-12")[1]
    assert _dob("1975-03-12", "1975-03-12")[1] == {}
