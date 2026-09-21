"""Issue #164: resolve_ubo_chain() is dead code causing confusion."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases import manager  # noqa: E402


def test_resolve_ubo_chain_removed():
    """Issue #164: resolve_ubo_chain() should be removed as dead code."""
    assert not hasattr(manager, "resolve_ubo_chain"), \
        "resolve_ubo_chain() should be removed (Issue #164)"
