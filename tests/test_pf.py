"""Proliferation-financing classification tests.

Law 10/2025 makes PF a standalone offence rather than a subtype of sanctions,
so PF and TF designations must never be conflated. Both are freezable; they are
different offences with different reports.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.screening.pf import (  # noqa: E402
    classify_programs,
    is_proliferation,
    is_terrorism,
    obligation_note,
)


class TestProgrammeClassification:
    @pytest.mark.parametrize(
        "program",
        ["UN-SC1718", "UN-SC1737", "UN-SC2231", "NPWMD", "DPRK2", "IFSR"],
    )
    def test_proliferation_regimes(self, program: str) -> None:
        assert is_proliferation([program]), f"{program} should classify as PF"

    @pytest.mark.parametrize("program", ["UN-SCISIL", "UN-SC1988", "AE-UNSC1373"])
    def test_terrorism_regimes(self, program: str) -> None:
        assert is_terrorism([program]), f"{program} should classify as TF"
        assert not is_proliferation([program]), f"{program} must not classify as PF"

    @pytest.mark.parametrize("program", ["UN-SC1970", "UN-SC1533", "UN-SC1591"])
    def test_country_regimes_are_neither(self, program: str) -> None:
        """Libya, DRC and Sudan designations are sanctions but neither PF nor TF."""
        assert classify_programs([program]) == set()

    def test_unknown_programme_defaults_to_neither(self) -> None:
        """An unrecognised regime must not fall into a category by accident."""
        assert classify_programs(["UN-SC9999", "SOMETHING-ELSE"]) == set()

    def test_empty_and_none_safe(self) -> None:
        assert classify_programs(None) == set()
        assert classify_programs([]) == set()
        assert classify_programs(["", "   "]) == set()

    def test_case_insensitive(self) -> None:
        assert is_proliferation(["un-sc1718"])

    def test_mbs_is_not_a_recognised_programme_code(self) -> None:
        """"MBS" was previously listed in PF_OFAC_CODES with no documented
        meaning, no other reference in the codebase, and no test coverage.
        It is not a real OFAC sanctions programme tag; treating it as one
        risks misclassifying an unrelated hit as proliferation financing.
        Regression test for the 2026-08-23 continuous-improvement finding."""
        assert classify_programs(["MBS"]) == set()
        assert not is_proliferation(["MBS"])

    def test_entity_can_be_both(self) -> None:
        cats = classify_programs(["UN-SC1718", "UN-SCISIL"])
        assert cats == {"proliferation", "terrorism"}


class TestObligationNotes:
    def test_pf_note_names_the_standalone_offence(self) -> None:
        note = obligation_note({"proliferation"})
        assert "PROLIFERATION FINANCING" in note
        assert "10 of 2025" in note

    def test_pf_takes_precedence_over_tf(self) -> None:
        """Where both apply, the PF obligation is the one surfaced first."""
        assert "PROLIFERATION" in obligation_note({"proliferation", "terrorism"})

    def test_tf_note(self) -> None:
        assert "TERRORISM FINANCING" in obligation_note({"terrorism"})

    def test_plain_sanctions_note(self) -> None:
        note = obligation_note(set())
        assert "SANCTIONS match" in note

    @pytest.mark.parametrize(
        "cats", [set(), {"terrorism"}, {"proliferation"}, {"proliferation", "terrorism"}]
    )
    def test_every_note_states_the_core_duties(self, cats: set[str]) -> None:
        """Freeze without delay and do not tip off apply in every case."""
        note = obligation_note(cats)
        assert "without delay" in note
        assert "tip off" in note
