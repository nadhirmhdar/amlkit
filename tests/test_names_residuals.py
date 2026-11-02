"""WP-24: name-screening residuals N3 (invisible/homoglyph bypasses) and F2
(extra-token queries, homoglyph spellings).

Probe strings are copied from the 1 Nov red-team script
(probe_unicode_bypass.py) as \\u escapes so the invisible characters survive
editors. Each must now HIT its target listed entry through the real engine.
Real in-memory SQLite, same synthetic watchlist as test_matching.py.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.match import cache  # noqa: E402
from amlkit.match.engine import screen  # noqa: E402
from amlkit.match.scorer import DEFAULT_THRESHOLD, name_score  # noqa: E402
from amlkit.names.arabic import (  # noqa: E402
    blocking_keys,
    canonical_key,
    canonical_tokens,
    clean_name_text,
    normalize_arabic,
)
from amlkit.names.confusables import fold_confusables  # noqa: E402

WATCHLIST = [
    ("SYN-2", "Person", "BILAL ALI AL-WAFI", ["بلال علي الوافي"], "ly", None, "male"),
    ("SYN-3", "Person", "MOHAMMAD DAWOOD MUZAMMIL", ["محمد داود مزمل"], "pk", "1980-01-01", "male"),
    ("SYN-6", "Person", "MOHAMMED ALI", [], "ae", None, "male"),
]

# (label, query, expected listed caption) -- strings from the red-team probe.
PROBES = [
    ("ideographic space inside token", "BI　LAL ALI AL-WAFI", "BILAL ALI AL-WAFI"),
    ("Greek consonant homoglyph (Beta)", "ΒILAL ALI AL-WAFI", "BILAL ALI AL-WAFI"),
    ("Cyrillic homoglyph (Ve) in BILAL", "ВILAL ALI AL-WAFI", "BILAL ALI AL-WAFI"),
    ("Cyrillic lookalike letters throughout", "ВІLАL АLІ АL-WAFІ", "BILAL ALI AL-WAFI"),
    ("Urdu yeh-barree", "بلال علے الوافے", "BILAL ALI AL-WAFI"),
    ("extra token", "BILAL ALI AL-WAFI HASSAN", "BILAL ALI AL-WAFI"),
    ("extra token, short listed name", "Mohammed Ali Hassan", "MOHAMMED ALI"),
]


@pytest.fixture()
def conn():
    cache.invalidate()
    c = connect(":memory:")
    ds = upsert_dataset(c, "test_list", "Synthetic Test List", is_mandatory=True)
    now = utcnow()
    for sid, schema, caption, aliases, country, dob, gender in WATCHLIST:
        cur = c.execute(
            """INSERT INTO entities (dataset_id, source_id, schema_type, caption,
               countries, birth_date, gender, topics, raw, first_seen, last_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (ds, sid, schema, caption, f'["{country}"]', dob, gender, '["sanction"]', "{}", now, now),
        )
        eid = cur.lastrowid
        for i, nm in enumerate([caption, *aliases]):
            c.execute(
                "INSERT INTO entity_names (entity_id, name, name_type, canonical_key, script)"
                " VALUES (?,?,?,?,?)",
                (eid, nm, "primary" if i == 0 else "alias", canonical_key(nm),
                 "arabic" if i else "latin"),
            )
            for tok in blocking_keys(nm):
                c.execute("INSERT OR IGNORE INTO name_tokens (token, entity_id) VALUES (?,?)", (tok, eid))
    c.execute("UPDATE datasets SET last_refresh=?, entity_count=? WHERE id=?",
              (now, len(WATCHLIST), ds))
    c.commit()
    yield c
    c.close()
    cache.invalidate()


@pytest.mark.parametrize("label,query,target", PROBES, ids=[p[0] for p in PROBES])
def test_probe_hits_target_via_engine(conn, label, query, target) -> None:
    r = screen(conn, query, org_id=1, persist=False)
    assert not r.unscreenable
    assert target in {h.caption for h in r.hits}, f"{label}: no hit on {target!r}"
    assert max(h.score for h in r.hits if h.caption == target) >= DEFAULT_THRESHOLD


def test_red_team_cyrillic_probe_string_folds_to_latin(conn) -> None:
    # The probe string as written ("AL-<Cyrillic Ve>AFI") is B, not W: it is a
    # different Latin spelling once folded, not a spoof of WAFI. Assert the
    # fold, not a hit (see report).
    q = "BILAL ALI AL-ВAFI"
    assert clean_name_text(q) == "BILAL ALI AL-BAFI"
    assert max((h.score for h in screen(conn, q, org_id=1, persist=False).hits), default=0) >= 0


def test_genuine_cyrillic_name_stays_unscreenable(conn) -> None:
    r = screen(conn, "Иван Петров", org_id=1, persist=False)
    assert r.unscreenable and not r.hits


# ---- N3 unit behaviour ---------------------------------------------------

def _zs_chars() -> list[str]:
    return [chr(c) for c in range(0x110000) if unicodedata.category(chr(c)) == "Zs"]


@pytest.mark.parametrize("sp", _zs_chars(), ids=lambda c: f"U+{ord(c):04X}")
def test_every_zs_is_a_token_separator(sp) -> None:
    assert canonical_tokens(f"BILAL{sp}ALI{sp}AL-WAFI") == canonical_tokens("BILAL ALI AL-WAFI")


def test_persian_urdu_letters_map_to_arabic() -> None:
    assert normalize_arabic("ے") == "ي"   # yeh barree
    assert normalize_arabic("ی") == "ي"   # farsi yeh
    assert normalize_arabic("ک") == "ك"   # keheh -> kaf
    assert canonical_key("بلال علے") == canonical_key("بلال علي")


def test_fold_confusables_table() -> None:
    cyr = "аеорсухіјѕАВЕКМНОРСТХ"
    assert fold_confusables(cyr) == "aeopcyxijsABEKMHOPCTX"
    greek = "ΑΒΕΖΗΙΚΜΝΟΡΤΥΧο"
    assert fold_confusables(greek) == "ABEZHIKMNOPTYXo"
    assert fold_confusables("") == ""
    assert fold_confusables("Ａｌｉ") == "Ali"  # NFKC


# ---- F2: extra-token containment ------------------------------------------

def test_extra_token_not_below_threshold() -> None:
    for q in ("Mohammed Ali Hassan", "Mohammed Ali Hassan Khan Al Suwaidi"):
        s, d = name_score(q, "Mohammed Ali")
        assert DEFAULT_THRESHOLD <= s < 1.0, (q, s)
        assert "token_containment" in d


def test_containment_is_bounded_and_not_applied_when_listed_token_missing() -> None:
    # listed token "Dawood" absent -> no containment boost
    s, d = name_score("Mohammad Hassan Khan", "Mohammad Dawood Muzammil")
    assert s < DEFAULT_THRESHOLD and "token_containment" not in d
    # single-token query / single-token listed name never boosted
    s, _ = name_score("Mohammed", "Mohammad Dawood")
    assert s < DEFAULT_THRESHOLD
    s, d = name_score("Saddam Hassan Khan", "Saddam")
    assert "token_containment" not in d
    # many extras: penalty is capped, never reaches exact
    s, _ = name_score("Mohammed Ali A B C D E F", "Mohammed Ali")
    assert DEFAULT_THRESHOLD <= s < 1.0


# ---- no-regression snapshot ------------------------------------------------

def test_no_existing_score_decreases() -> None:
    """Scores for the existing fixtures, generated from master e8ddf26 before
    this change (tests/data/scorer_snapshot_master.json), may only go up."""
    snap = json.loads((Path(__file__).parent / "data" / "scorer_snapshot_master.json").read_text("utf8"))
    assert len(snap) > 500
    lower = []
    for key, old in snap.items():
        q, c = key.split("|||")
        new = round(name_score(q, c)[0], 6)
        if new < old - 1e-9:
            lower.append((q, c, old, new))
    assert not lower, lower[:10]
