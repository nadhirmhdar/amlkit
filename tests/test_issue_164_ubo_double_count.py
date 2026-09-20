"""Issue #164: resolve_ubo_chain() is dead code - remove it.

resolve_ubo_chain() is only called from tests, not production code. Since it's
unused, it should be removed to avoid confusion.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_resolve_ubo_chain_removed():
    """resolve_ubo_chain should be removed as dead code."""
    from amlkit.cases import manager

    # Verify that resolve_ubo_chain is no longer in the module
    assert not hasattr(manager, "resolve_ubo_chain"), \
        "resolve_ubo_chain() should be removed as it's unused dead code"
