"""Name canonicalisation tests.

These are the foundation of match quality: if canonicalisation regresses,
every score above it regresses silently. Hermetic -- no network, no database.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.names.arabic import (  # noqa: E402
    canonical_key,
    canonical_tokens,
    consonant_skeleton,
    has_arabic_script,
    normalize_arabic,
    tokenize,
    transliterate_arabic,
)

# Arabic written as escapes so the file survives any editor or console encoding.
AR_MOHAMMED_BIN_RASHID = "محمد بن راشد المكتوم"
AR_ABDULLAH_SAEED = "عبدالله سعيد"
AR_HUSSEIN_ALI = "حسين علي"
AR_MOHAMMED_DIACRITICS = "مُحَمَّد"


class TestTransliterationVariants:
    """The core claim: spelling variants of one name collapse to one key."""

    @pytest.mark.parametrize(
        "a,b",
        [
            ("Mohammed bin Rashid Al Maktoum", "Muhammad b. Rashed al-Maktum"),
            ("Mohd. Rashid", "Mohammed Rashid"),
            ("Abdul Rahman Hussein", "Abd al-Rahman Hussain"),
            ("Youssef Ibrahim", "Yusuf Ebrahim"),
            ("Hussein Ali", "Husayn Aly"),
            ("Khaled Al Nasser", "Khalid Al-Nasir"),
            ("Abdullah Al Suwaidi", "Abdalla Al-Suwaidi"),
            ("Mariam Al Zaabi", "Maryam Al Zaabi"),
        ],
    )
    def test_variants_converge(self, a: str, b: str) -> None:
        assert canonical_key(a) == canonical_key(b), f"{a!r} != {b!r}"

    @pytest.mark.parametrize(
        "a,b",
        [
            ("Mohammed Ali", "Ahmed Ali"),
            ("Khalid Saeed", "Omar Saeed"),
            ("Fatima Al Zaabi", "Fatima Al Nuaimi"),
            ("Ibrahim Hassan", "Ibrahim Hussein"),
        ],
    )
    def test_distinct_names_stay_distinct(self, a: str, b: str) -> None:
        """Over-normalising is as dangerous as under-normalising."""
        assert canonical_key(a) != canonical_key(b), f"collapsed {a!r} into {b!r}"


class TestNameOrder:
    def test_order_independent(self) -> None:
        """Arabic name chains arrive in inconsistent order across documents."""
        assert canonical_key("Rashid Mohammed") == canonical_key("Mohammed Rashid")

    def test_particles_ignored(self) -> None:
        assert canonical_key("Ahmed bin Ali al-Hasnawi") == canonical_key("Ahmed Ali Hasnawi")


class TestArabicScript:
    def test_detects_script(self) -> None:
        assert has_arabic_script(AR_HUSSEIN_ALI)
        assert not has_arabic_script("Hussein Ali")

    def test_diacritics_removed(self) -> None:
        assert normalize_arabic(AR_MOHAMMED_DIACRITICS) == "محمد"

    @pytest.mark.parametrize(
        "latin,arabic",
        [
            ("Mohammed bin Rashid Al Maktoum", AR_MOHAMMED_BIN_RASHID),
            ("Abdullah Saeed", AR_ABDULLAH_SAEED),
            ("Hussein Ali", AR_HUSSEIN_ALI),
        ],
    )
    def test_cross_script_convergence(self, latin: str, arabic: str) -> None:
        """The differentiator: either script must reach the same canonical key."""
        assert canonical_key(latin) == canonical_key(arabic)

    def test_arabic_produces_tokens(self) -> None:
        """Guards a real bug: Arabic once canonicalised to an empty token list,
        which would have made every Arabic query match nothing at all."""
        assert canonical_tokens(AR_HUSSEIN_ALI), "Arabic script yielded no tokens"

    def test_waw_positional(self) -> None:
        """Waw is a consonant word-initially, a long vowel elsewhere."""
        assert transliterate_arabic("وليد").startswith("w")


class TestOverNormalisation:
    """Guards against collapsing genuinely different names together.

    A wrong-person match is the worst failure a screening system has: it
    attaches a real customer to someone else's designation. These cases were
    all live bugs found against real data.
    """

    @pytest.mark.parametrize(
        "a,b,why",
        [
            ("Mansour", "Mansoori", "nisba suffix makes a family name"),
            ("Ahmed Al Mansoori", "Mansoor Ahmed", "common Emirati surname vs given name"),
            ("Saad", "Saeed", "distinct given names, same consonants"),
            ("Hassan", "Hussein", "distinct given names, same consonants"),
            ("Saleh", "Salehi", "nisba suffix"),
        ],
    )
    def test_distinct_names_do_not_merge(self, a: str, b: str, why: str) -> None:
        assert canonical_key(a) != canonical_key(b), f"{a}/{b} merged: {why}"

    @pytest.mark.parametrize(
        "a,b",
        [
            ("Al Hasnawi", "Al-Hasnawi"),
            ("Mansoori", "Al Mansouri"),
            ("Majid", "Majed"),
        ],
    )
    def test_nisba_names_still_self_match(self, a: str, b: str) -> None:
        """Preserving the suffix must not stop a name matching itself."""
        assert canonical_key(a) == canonical_key(b)

    def test_ambiguous_skeletons_are_excluded(self) -> None:
        """Ambiguous skeletons must not silently resolve to a first-registered name."""
        from amlkit.names.arabic import _AMBIGUOUS_SKELETONS, _SKELETON_INDEX

        assert _AMBIGUOUS_SKELETONS, "expected known collisions to be detected"
        for skel in _AMBIGUOUS_SKELETONS:
            assert skel not in _SKELETON_INDEX

    def test_every_arabic_form_target_is_canonical(self) -> None:
        """An ARABIC_FORMS target absent from the variant table falls through to
        the skeleton and can be absorbed into a different name."""
        from amlkit.names.arabic import ARABIC_FORMS, VARIANT_TABLE

        missing = sorted({t for t in ARABIC_FORMS.values() if t not in VARIANT_TABLE})
        assert not missing, f"unregistered canonical targets: {missing}"

    @pytest.mark.parametrize(
        "arabic,expected",
        [("سعد", "saad"), ("سعيد", "saeed"), ("حسن", "hassan"), ("حسين", "hussein")],
    )
    def test_arabic_disambiguates_where_latin_cannot(self, arabic: str, expected: str) -> None:
        """Arabic orthography distinguishes these even though consonants do not."""
        assert canonical_key(arabic) == expected


class TestSkeleton:
    def test_waw_dropped_medially_for_cross_script_alignment(self) -> None:
        """Arabic waw romanises as 'w' or 'ou/u' depending on the source;
        dropping it medially on both sides keeps the scripts aligned."""
        assert canonical_key("Hasnawi") == canonical_key("حسناوي")

    def test_vowel_drift_absorbed(self) -> None:
        assert consonant_skeleton("hussein") == consonant_skeleton("hussain")

    def test_doubled_consonants_collapse(self) -> None:
        assert consonant_skeleton("abdullah") == consonant_skeleton("abdulah")

    def test_digraphs_stable(self) -> None:
        assert consonant_skeleton("khalid") == consonant_skeleton("khaled")


class TestTokenize:
    def test_particles_separated(self) -> None:
        content, particles = tokenize("Mohammed bin Rashid Al Maktoum")
        assert "bin" in particles and "al" in particles
        assert "bin" not in content and "al" not in content

    def test_theophoric_compound_rejoined(self) -> None:
        """'Abd al-Rahman' is one name, not two or three."""
        assert canonical_tokens("Abd al Rahman") == canonical_tokens("Abdulrahman")

    def test_empty_input(self) -> None:
        assert tokenize("") == ([], [])
        assert canonical_key("") == ""
