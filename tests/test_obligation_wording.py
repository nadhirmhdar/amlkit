"""CS-23: obligation wording is decided by dataset first, category second.

An entry from a dataset that is not the UN Consolidated List or the UAE Local
Terrorist List never gets freeze wording, whatever its programme category.
"""

from __future__ import annotations

import itertools

import pytest

from amlkit.screening.pf import (
    NON_UAE_SANCTIONS_OBLIGATION,
    PEP_OBLIGATION,
    OTHER_OBLIGATION,
    obligation_for_category,
    obligation_note,
)

CATEGORIES = {
    "proliferation": {"proliferation"},
    "terrorism": {"terrorism"},
    "sanction": set(),
    "pep": set(),
    "other": set(),
}
NON_UAE = ["us_ofac_sdn", "eu_fsf", "gb_hmt_sanctions", "some_other_list"]
UAE = ["un_consolidated", "un_sc_sanctions", "ae_local_terrorists", "eocn_local"]


@pytest.mark.parametrize("category,dataset", list(itertools.product(CATEGORIES, NON_UAE)))
def test_non_uae_dataset_never_freeze(category, dataset):
    note = obligation_for_category(category, CATEGORIES[category], dataset)
    assert "freeze without delay" not in note.lower()
    if category in ("proliferation", "terrorism", "sanction"):
        assert note == NON_UAE_SANCTIONS_OBLIGATION
        assert "enhanced due diligence" in note and "STR/SAR" in note
    elif category == "pep":
        assert note == PEP_OBLIGATION
    else:
        assert note == OTHER_OBLIGATION


@pytest.mark.parametrize("category", ["proliferation", "terrorism"])
@pytest.mark.parametrize("dataset", NON_UAE)
def test_obligation_note_checks_dataset_before_category(category, dataset):
    note = obligation_note(CATEGORIES[category], dataset)
    assert note == NON_UAE_SANCTIONS_OBLIGATION


@pytest.mark.parametrize("category,dataset", list(itertools.product(
    ["proliferation", "terrorism", "sanction"], UAE)))
def test_uae_datasets_keep_freeze_wording(category, dataset):
    note = obligation_for_category(category, CATEGORIES[category], dataset)
    assert "Freeze without delay" in note


@pytest.mark.parametrize("category", ["proliferation", "terrorism", "sanction"])
def test_no_dataset_keeps_freeze_wording(category):
    # A UN listing cannot be ruled out when the dataset is unknown.
    assert "Freeze without delay" in obligation_for_category(
        category, CATEGORIES[category], None)
