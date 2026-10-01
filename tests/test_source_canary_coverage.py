"""Guard against silent coverage loss in the source canary.

The daily upstream canary (.github/workflows/source-canary.yml) enforces a
per-source minimum entity-count floor via an ``EXPECTED`` dict keyed by
adapter ``.key``. That dict is looked up with ``EXPECTED.get(res.dataset, 1)``,
so a source WITHOUT an explicit floor silently falls back to a floor of 1 —
meaning a newly added source could shrink to a single entity and still pass.
That is the exact silent-coverage-loss failure the canary exists to prevent.

``scripts/heartbeat.ALL_SOURCES`` is already the single source of truth for
WHICH sources are screened. This test ties the canary's floor table to that
same list: add a source to ``ALL_SOURCES`` and you are forced to declare a
real floor for it, or this test fails. It is a static check (it parses the
workflow YAML) and needs no network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.heartbeat import ALL_SOURCES

CANARY = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "source-canary.yml"
)


def _expected_floor_keys() -> list[str]:
    """Parse the EXPECTED = { ... } block out of the canary workflow."""
    text = CANARY.read_text(encoding="utf-8")
    m = re.search(r"EXPECTED\s*=\s*\{(.*?)\}", text, re.S)
    assert m, "could not find the EXPECTED floor dict in source-canary.yml"
    return re.findall(r'"([a-z0-9_]+)"\s*:', m.group(1))


def test_canary_workflow_exists():
    assert CANARY.is_file(), f"source canary workflow not found at {CANARY}"


def test_every_source_has_a_declared_floor():
    """Every adapter in ALL_SOURCES must have an explicit floor in EXPECTED.

    Without this, EXPECTED.get(dataset, 1) silently applies a floor of 1 to
    any source lacking a declared minimum — defeating the shrink-detection
    the canary is meant to provide.
    """
    floor_keys = set(_expected_floor_keys())
    source_keys = [factory().key for factory in ALL_SOURCES]

    missing = [k for k in source_keys if k not in floor_keys]
    assert not missing, (
        "sources in scripts.heartbeat.ALL_SOURCES have no entity-count floor "
        f"in source-canary.yml's EXPECTED dict: {missing}. Add an explicit "
        "floor so the canary can catch a source that shrinks."
    )


def test_floors_are_sane_positive_integers():
    """A floor of 1 (the silent default) is a mistake; floors must be real."""
    text = CANARY.read_text(encoding="utf-8")
    m = re.search(r"EXPECTED\s*=\s*\{(.*?)\}", text, re.S)
    assert m
    pairs = re.findall(r'"([a-z0-9_]+)"\s*:\s*(\d+)', m.group(1))
    assert pairs, "no floor entries parsed from EXPECTED"
    for key, value in pairs:
        assert int(value) > 1, (
            f"floor for {key} is {value}; a floor of 0 or 1 is the silent "
            "default and provides no shrink protection"
        )


def test_no_stale_floor_for_removed_source():
    """A floor key with no matching source means ALL_SOURCES drifted away."""
    floor_keys = _expected_floor_keys()
    source_keys = {factory().key for factory in ALL_SOURCES}
    stale = [k for k in floor_keys if k not in source_keys]
    assert not stale, (
        "source-canary.yml declares entity-count floors for sources no longer "
        f"in scripts.heartbeat.ALL_SOURCES: {stale}. Remove the stale floor(s)."
    )
