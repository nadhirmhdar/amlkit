"""One politically exposed person, however many lists carry them, is one hit."""
import json

import pytest

from amlkit.db import connect
from amlkit.ingest import loader
from amlkit.ingest.base import SourceEntity
from amlkit.match.engine import screen


@pytest.fixture(autouse=True)
def _fresh_token_cache():
    """match.cache is process-global (token -> entity ids) and not keyed by
    database; production invalidates it after every refresh, so do the same."""
    from amlkit.match import cache
    cache.invalidate()
    yield
    cache.invalidate()


class _Adapter:
    def __init__(self, key, entities):
        self.key = key
        self.title = key
        self.publisher = key
        self.source_url = "https://example.invalid"
        self.licence = "test"
        self.is_mandatory = False
        self._entities = entities

    def fetch(self):
        return repr((self.key, self._entities, id(self))).encode()

    def parse(self, payload):
        for sid, name, countries, topics in self._entities:
            yield SourceEntity(
                source_id=sid, schema_type="Person", caption=name, names=[],
                countries=list(countries), birth_date=None, gender=None,
                topics=list(topics), programs=[], identifiers=[], listed_at=None, raw={},
            )


def _load(conn, key, entities):
    loader.load(conn, _Adapter(key, entities))


def _db(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    conn.execute("INSERT INTO organizations (id, name, slug, status, created_at) VALUES (1,'T','t','active','2026-01-01')")
    conn.commit()
    return conn


def test_same_pep_on_two_lists_and_twice_on_one_is_a_single_hit_and_alert(tmp_path):
    conn = _db(tmp_path)
    _load(conn, "us_cia_world_leaders", [("c1", "Amit SHAH", ["India"], ["role.pep"]),
                                         ("c2", "Amit SHAH", ["India"], ["role.pep"])])
    _load(conn, "wikidata_ministers", [("WD-1", "Amit Shah", ["India"], ["role.pep"])])
    res = screen(conn, "Amit Shah", org_id=1, country="IN")
    assert len(res.hits) == 1 and res.alerts_created == 1
    also = res.hits[0].detail["also_listed"]
    assert len(also) == 2
    assert {a["dataset"] for a in also} == {"us_cia_world_leaders", "wikidata_ministers"}
    # evidence of what was absorbed is stored on the one alert
    row = conn.execute("SELECT score_detail FROM alerts").fetchone()
    assert len(json.loads(row["score_detail"])["also_listed"]) == 2
    assert conn.execute("SELECT COUNT(*) c FROM alerts").fetchone()["c"] == 1


def test_choice_of_kept_hit_is_stable(tmp_path):
    conn = _db(tmp_path)
    _load(conn, "wikidata_ministers", [("WD-1", "Amit Shah", ["India"], ["role.pep"])])
    _load(conn, "us_cia_world_leaders", [("c1", "Amit SHAH", ["India"], ["role.pep"])])
    first = screen(conn, "Amit Shah", org_id=1, persist=False).hits[0]
    again = screen(conn, "Amit Shah", org_id=1, persist=False).hits[0]
    assert (first.entity_id, first.dataset) == (again.entity_id, again.dataset)
    assert first.dataset == "us_cia_world_leaders"


def test_same_name_in_different_countries_is_not_merged(tmp_path):
    conn = _db(tmp_path)
    _load(conn, "us_cia_world_leaders", [("c1", "Amit SHAH", ["India"], ["role.pep"]),
                                         ("c2", "Amit SHAH", ["Nepal"], ["role.pep"])])
    assert len(screen(conn, "Amit Shah", org_id=1, persist=False).hits) == 2


def test_sanctions_hits_are_never_merged(tmp_path):
    conn = _db(tmp_path)
    _load(conn, "us_ofac_sdn", [("o1", "Amit Shah", ["India"], ["sanction"])])
    _load(conn, "un_sc_consolidated", [("u1", "Amit Shah", ["India"], ["sanction"])])
    _load(conn, "wikidata_ministers", [("WD-1", "Amit Shah", ["India"], ["role.pep"])])
    res = screen(conn, "Amit Shah", org_id=1, persist=False)
    assert len(res.hits) == 3
    assert not any("also_listed" in h.detail for h in res.hits)


def test_pep_who_is_also_sanctioned_stays_separate_from_the_pep_only_hit(tmp_path):
    conn = _db(tmp_path)
    _load(conn, "us_cia_world_leaders", [("c1", "Amit Shah", ["India"], ["role.pep"])])
    _load(conn, "us_ofac_sdn", [("o1", "Amit Shah", ["India"], ["sanction", "role.pep"])])
    assert len(screen(conn, "Amit Shah", org_id=1, persist=False).hits) == 2


# ---------------------------------------------------------- the web page
from tests.test_api import _csrf, client  # noqa: E402,F401


def test_screen_page_shows_one_card_and_names_the_other_lists(client):
    import os
    conn = connect(os.environ["AMLKIT_DB"])
    _load(conn, "us_cia_world_leaders", [("c1", "Amit SHAH", ["India"], ["role.pep"]),
                                         ("c2", "Amit SHAH", ["India"], ["role.pep"])])
    _load(conn, "wikidata_ministers", [("WD-1", "Amit Shah", ["India"], ["role.pep"])])
    r = client.post("/screen", data={"name": "Amit Shah", "nationality": "IN",
                                     "csrf_token": _csrf(client)})
    assert r.status_code == 200
    assert r.text.count('class="alert-card"') == 1
    assert "Same person also listed on:" in r.text
    assert "wikidata_ministers" in r.text
