"""H13: Risk scoring must fail-safe on invalid input values.

Unknown/misspelled risk-factor values currently score zero points due to
.get(key, 0) defaults, which incorrectly lowers the risk rating. Invalid
inputs should raise errors, not silently score as lowest-risk.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


class TestRiskScoringFailSafe:
    """Risk scoring must fail-safe (reject or default to high-risk) on invalid values."""

    def test_misspelled_jurisdiction_tier_raises_error(self) -> None:
        """Misspelled jurisdiction_tier (e.g., trailing space) must raise ValueError.

        Production change that makes this pass: risk/model.py:assess() must validate
        jurisdiction_tier against an allowlist before scoring, and raise ValueError
        for invalid values. Currently 'fatf_blacklist ' (with space) scores 0 instead
        of the correct 60 points, lowering the risk rating.
        """
        from amlkit.risk.model import assess, CustomerProfile

        # This should raise ValueError for invalid jurisdiction_tier
        with pytest.raises(ValueError, match="jurisdiction_tier"):
            assess(CustomerProfile(
                jurisdiction_tier="fatf_blacklist ",  # trailing space
                sector="real_estate",
                ownership_state="verified",
                delivery_channel="face_to_face",
                cash_level="high_cash",
                adverse_media="none",
                structure="natural_person",
            ))

    def test_invalid_structure_raises_error(self) -> None:
        """Invalid structure values must raise ValueError."""
        from amlkit.risk.model import assess, CustomerProfile

        with pytest.raises(ValueError, match="structure"):
            assess(CustomerProfile(
                jurisdiction_tier="standard",
                sector="real_estate",
                ownership_state="verified",
                delivery_channel="face_to_face",
                cash_level="non_cash",
                adverse_media="none",
                structure="INVALID_STRUCTURE",
            ))

    def test_invalid_delivery_channel_raises_error(self) -> None:
        """Invalid delivery_channel values must raise ValueError."""
        from amlkit.risk.model import assess, CustomerProfile

        with pytest.raises(ValueError, match="delivery_channel"):
            assess(CustomerProfile(
                jurisdiction_tier="standard",
                sector="real_estate",
                ownership_state="verified",
                delivery_channel="invalid_channel",
                cash_level="non_cash",
                adverse_media="none",
                structure="natural_person",
            ))

    def test_invalid_cash_level_raises_error(self) -> None:
        """Invalid cash_level values must raise ValueError."""
        from amlkit.risk.model import assess, CustomerProfile

        with pytest.raises(ValueError, match="cash_level"):
            assess(CustomerProfile(
                jurisdiction_tier="standard",
                sector="real_estate",
                ownership_state="verified",
                delivery_channel="face_to_face",
                cash_level="wrong_value",
                adverse_media="none",
                structure="natural_person",
            ))
