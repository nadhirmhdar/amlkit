"""Unicode robustness of name canonicalisation and screening (lead finding L-2).

Two silent-miss defects, both invisible to a human looking at the screen:

  1. Arabic *presentation forms* (U+FB50-FDFF, U+FE70-FEFF) -- what PDF/Word
     copy-paste emits -- were not recognised as Arabic script, so the name
     canonicalised to '' and screening found 0 candidates ("clear").
  2. Zero-width / bidi / BOM format characters (Unicode category Cf) inside a
     Latin name split the token, so an exact listed name was missed.

Real SQLite, no DB mocks, same style as test_matching.py.
"""

from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, upsert_dataset, utcnow  # noqa: E402
from amlkit.match.engine import screen  # noqa: E402
from amlkit.names.arabic import (  # noqa: E402
    blocking_keys,
    canonical_key,
    canonical_tokens,
    clean_name_text,
    has_arabic_script,
    normalize_arabic,
)

LISTED_LATIN = "Ahmed Abd Al-Jaleel Al-Hasnawi"
LISTED_ARABIC = "أحمد عبد الجليل الحسناوي"
LISTED_ARABIC_2 = "محمد داود مزمل"

WATCHLIST = [
    ("SYN-1", "Person", LISTED_LATIN, [LISTED_ARABIC], "ly", "1975-03-12", "male"),
    ("SYN-3", "Person", "MOHAMMAD DAWOOD MUZAMMIL", [LISTED_ARABIC_2], "pk", "1980-01-01", "male"),
    ("SYN-5", "Person", "FOAD SALEHI", ["فؤاد صالحي"], "ir", "1968-07-20", "male"),
]


def _presentation_form_map() -> dict[str, str]:
    """Base Arabic letter -> a presentation-form code point that NFKC folds to it.

    Built from the Unicode database rather than hand-typed so the test spells
    names exactly the way a PDF would, without opaque literals.
    """
    out: dict[str, str] = {}
    for cp in list(range(0xFB50, 0xFE00)) + list(range(0xFE70, 0xFF00)):
        ch = chr(cp)
        base = unicodedata.normalize("NFKC", ch)
        if len(base) == 1 and base != ch and base not in out:
            out[base] = ch
    return out


_PF = _presentation_form_map()


def to_presentation_forms(text: str) -> str:
    """Re-spell Arabic letters as presentation forms; leave everything else."""
    return "".join(_PF.get(ch, ch) for ch in text)


FORMAT_CHARS = {
    "ZWSP": "\u200b",
    "ZWNJ": "\u200c",
    "ZWJ": "\u200d",
    "LRM": "\u200e",
    "RLM": "\u200f",
    "LRE": "\u202a",
    "PDF": "\u202c",
    "RLO": "\u202e",
    "WJ": "\u2060",
    "BOM": "\ufeff",
    "SHY": "\u00ad",
}


@pytest.fixture()
def conn():
    # match.cache is a process-global token->entity-id map; entity ids from an
    # earlier test's database would otherwise leak into this one.
    from amlkit.match import cache

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


@pytest.fixture()
def org_id(conn) -> int:
    row = conn.execute(
        "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id",
        ("Test Firm", "test-firm", "active", utcnow()),
    ).fetchone()
    conn.commit()
    return row["id"]


# --------------------------------------------------------------------------
# Harness sanity: the presentation-form spelling really is different text
# --------------------------------------------------------------------------

def test_presentation_form_helper_produces_different_codepoints() -> None:
    pf = to_presentation_forms(LISTED_ARABIC)
    assert pf != LISTED_ARABIC
    assert any(0xFB50 <= ord(c) <= 0xFDFF or 0xFE70 <= ord(c) <= 0xFEFF for c in pf)
    # and it round-trips through NFKC to the original letters
    assert unicodedata.normalize("NFKC", pf) == LISTED_ARABIC


# --------------------------------------------------------------------------
# Presentation forms
# --------------------------------------------------------------------------

class TestPresentationForms:
    def test_has_arabic_script_recognises_presentation_forms(self) -> None:
        assert has_arabic_script(to_presentation_forms(LISTED_ARABIC))

    def test_has_arabic_script_raw_blocks_without_nfkc_folding(self) -> None:
        # FDFA-style / isolated forms are in the extended range regardless of
        # how they fold.
        assert has_arabic_script("ﻡ")  # MEEM isolated form (FE70 block)
        assert has_arabic_script("ﭐ")  # ALEF WASLA isolated form (FB50 block)

    @pytest.mark.parametrize("listed", [LISTED_ARABIC, LISTED_ARABIC_2, "فؤاد صالحي"])
    def test_canonical_key_matches_base_spelling(self, listed: str) -> None:
        pf = to_presentation_forms(listed)
        assert canonical_key(pf) != ""
        assert canonical_key(pf) == canonical_key(listed)

    def test_pf_arabic_matches_latin_transliteration(self) -> None:
        pf = to_presentation_forms(LISTED_ARABIC_2)
        assert canonical_key(pf) == canonical_key("Mohammad Dawood Muzammil")

    def test_lam_alef_ligature_form(self) -> None:
        # Lam-alef ligatures (U+FEFB/FEFC) are a typical PDF-copy artefact and
        # NFKC expands each to two letters. "Bilal" = beh + lam-alef(final) + lam.
        assert normalize_arabic("ﻻ") == "لا"
        bilal_pf = "ﺑﻼﻝ"
        assert canonical_key(bilal_pf) == canonical_key("بلال") == "bilal"

    def test_skeptic_repro_string(self) -> None:
        # Exact string from the skeptic repro (repro_skeptic/presentation_forms.py):
        # presentation forms of "Bilal"; used to canonicalise to ''.
        pf = "ﺏﻠﺎﻠ"
        assert has_arabic_script(pf)
        assert canonical_key(pf) == canonical_key("بلال") == "bilal"

    def test_normalize_arabic_folds_presentation_forms(self) -> None:
        assert normalize_arabic(to_presentation_forms(LISTED_ARABIC_2)) == normalize_arabic(LISTED_ARABIC_2)

    def test_screen_finds_listed_name_in_presentation_forms(self, conn, org_id) -> None:
        pf = to_presentation_forms(LISTED_ARABIC)
        res = screen(conn, pf, org_id=org_id, trigger="adhoc", persist=False)
        assert not res.clear
        assert not res.unscreenable
        assert res.candidates > 0
        assert res.hits[0].caption == LISTED_LATIN
        assert res.hits[0].score >= 0.99

    def test_screen_presentation_forms_same_result_as_base(self, conn, org_id) -> None:
        base = screen(conn, LISTED_ARABIC_2, org_id=org_id, persist=False)
        pf = screen(conn, to_presentation_forms(LISTED_ARABIC_2), org_id=org_id, persist=False)
        assert [h.entity_id for h in pf.hits] == [h.entity_id for h in base.hits]
        assert pf.hits and pf.hits[0].score == base.hits[0].score


# --------------------------------------------------------------------------
# Format (Cf) characters
# --------------------------------------------------------------------------

class TestFormatCharacters:
    @pytest.mark.parametrize("junk", FORMAT_CHARS.values(), ids=FORMAT_CHARS.keys())
    def test_format_char_inside_latin_token_does_not_split_it(self, junk: str) -> None:
        name = f"Mo{junk}hammad Dawood Muza{junk}mmil"
        assert canonical_tokens(name) == canonical_tokens("Mohammad Dawood Muzammil")
        assert canonical_key(name) == canonical_key("Mohammad Dawood Muzammil")

    @pytest.mark.parametrize("junk", FORMAT_CHARS.values(), ids=FORMAT_CHARS.keys())
    def test_format_char_adjacent_to_spaces_is_harmless(self, junk: str) -> None:
        name = f"{junk}FOAD{junk} {junk}SALEHI{junk}"
        assert canonical_key(name) == canonical_key("FOAD SALEHI")

    def test_format_chars_inside_arabic_name(self) -> None:
        name = " ".join("\u200c".join(tok) for tok in LISTED_ARABIC_2.split())
        assert name != LISTED_ARABIC_2
        assert canonical_key(name) == canonical_key(LISTED_ARABIC_2)

    def test_has_arabic_script_ignores_format_chars_in_latin(self) -> None:
        assert not has_arabic_script("Foad\u200b Salehi")

    def test_clean_name_text_strips_only_format_chars(self) -> None:
        assert clean_name_text("A\u200bB\u200dC\ufeffD") == "ABCD"
        assert clean_name_text("") == ""
        assert clean_name_text("Foad Salehi") == "Foad Salehi"

    def test_screen_exact_latin_name_with_zero_width_chars(self, conn, org_id) -> None:
        name = "FOAD\u200b SA\u200dLEHI\ufeff"
        res = screen(conn, name, org_id=org_id, persist=False)
        assert not res.clear
        assert res.hits[0].caption == "FOAD SALEHI"
        assert res.hits[0].score >= 0.99

    def test_screen_with_bidi_marks_around_name(self, conn, org_id) -> None:
        name = "\u202aMOHAMMAD DAWOOD\u202c \u200fMUZAMMIL\u200e"
        res = screen(conn, name, org_id=org_id, persist=False)
        assert res.hits and res.hits[0].caption == "MOHAMMAD DAWOOD MUZAMMIL"
        assert res.hits[0].score >= 0.99


# --------------------------------------------------------------------------
# Regression: ordinary names are unchanged
# --------------------------------------------------------------------------

class TestNoRegression:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("Mohammed bin Rashid", "mohammed rashid"),
            ("Muhammad b. Rashed", "mohammed rashid"),
            ("Mohd. B. Rashid", "mohammed rashid"),
            ("محمد بن راشد", "mohammed rashid"),
            ("Ahmed Al-Hasnawi", canonical_key("Ahmad al Hasnawi")),
        ],
    )
    def test_known_names_canonicalise_as_before(self, name: str, expected: str) -> None:
        assert canonical_key(name) == expected

    def test_arabic_diacritics_still_stripped(self) -> None:
        assert canonical_key("مُحَمَّد") == canonical_key("محمد")

    def test_latin_diacritics_still_folded(self) -> None:
        assert canonical_key("Fouad Saléhi") == canonical_key("Fouad Salehi")

    def test_latin_name_not_arabic(self) -> None:
        assert not has_arabic_script("Mohammed bin Rashid")
        assert has_arabic_script("محمد بن راشد")

    def test_screen_ordinary_names_unchanged(self, conn, org_id) -> None:
        latin = screen(conn, LISTED_LATIN, org_id=org_id, persist=False)
        arabic = screen(conn, LISTED_ARABIC, org_id=org_id, persist=False)
        assert latin.hits[0].score == 1.0 and arabic.hits[0].score == 1.0
        unrelated = screen(conn, "John Smith", org_id=org_id, persist=False)
        assert unrelated.clear and not unrelated.unscreenable


# --------------------------------------------------------------------------
# Fallback: letters that canonicalise to nothing must not read as "clear"
# --------------------------------------------------------------------------

class TestUnscreenableFallback:
    def test_letters_with_no_tokens_is_flagged_not_clear(self, conn, org_id) -> None:
        # Lone Arabic-block marks / unmapped letters canonicalise to ''.
        name = "ے"  # Arabic yeh barree: not in the transliteration table
        assert canonical_key(name) == ""
        res = screen(conn, name, org_id=org_id, persist=False)
        assert res.unscreenable
        assert not res.clear
        assert "UNSCREENABLE" in res.summary()

    def test_digits_only_stays_as_before(self, conn, org_id) -> None:
        res = screen(conn, "123", org_id=org_id, persist=False)
        assert not res.unscreenable
        assert res.candidates == 0

    def test_persisted_unscreenable_records_no_datasets(self, conn, org_id) -> None:
        res = screen(conn, "ے", org_id=org_id, persist=True)
        assert res.unscreenable
        row = conn.execute(
            "SELECT candidates, datasets_used FROM screenings WHERE id=?", (res.screening_id,)
        ).fetchone()
        assert row["candidates"] == 0
        assert row["datasets_used"] == "[]"
