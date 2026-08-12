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


class TestSkeleton:
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
