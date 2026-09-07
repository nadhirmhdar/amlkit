"""Ruleset cache reload tests.

`ruleset()` used to load ruleset.yaml once per process with no invalidation:
editing the file on a long-lived instance (a warm Cloud Run container, a
compliance officer's own machine) had no effect until the process restarted,
with nothing indicating the running process was scoring against stale rules.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import amlkit.risk.model as model  # noqa: E402


def _reset_cache() -> None:
    model._cache = None
    model._cache_mtime = None


class TestRulesetCacheReload:
    def setup_method(self) -> None:
        self._real_path = model.RULESET_PATH
        _reset_cache()

    def teardown_method(self) -> None:
        model.RULESET_PATH = self._real_path
        _reset_cache()

    def test_edited_ruleset_is_picked_up_without_restart(self, tmp_path) -> None:
        ruleset_copy = tmp_path / "ruleset.yaml"
        shutil.copyfile(self._real_path, ruleset_copy)
        model.RULESET_PATH = ruleset_copy

        first = model.ruleset()
        # Read the shipped version rather than pinning the literal: this test
        # is about the cache noticing an edit, not about which version is
        # current, and hardcoding it made every legitimate ruleset revision
        # fail here for no reason connected to what is being tested.
        shipped = first["version"]
        assert shipped and shipped != "2099.1.1"

        # Rewrite with a bumped version, forcing the mtime forward so the
        # change is observed even on filesystems with coarse mtime
        # resolution.
        text = ruleset_copy.read_text(encoding="utf-8")
        text = text.replace(f'version: "{shipped}"', 'version: "2099.1.1"', 1)
        assert '2099.1.1' in text, "version line not found; the edit under test never happened"
        ruleset_copy.write_text(text, encoding="utf-8")
        future = time.time() + 5
        os.utime(ruleset_copy, (future, future))

        second = model.ruleset()
        assert second["version"] == "2099.1.1"

    def test_unchanged_file_is_served_from_cache(self, tmp_path) -> None:
        ruleset_copy = tmp_path / "ruleset.yaml"
        shutil.copyfile(self._real_path, ruleset_copy)
        model.RULESET_PATH = ruleset_copy

        first = model.ruleset()
        second = model.ruleset()
        assert first is second
