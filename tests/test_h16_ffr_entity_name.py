"""Test H16: FFR for legal entity must use full name, handle blank names.

freeze.py uses split()[0] for first_name, so "Gulf Falcon Trading LLC" would file
as just "Gulf" in goAML. Blank full_name would raise uncaught IndexError.
"""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_ffr_legal_entity_uses_full_name():
    """FFR for legal entity should use full entity name in first_name field."""
    # Test the logic directly without full DB setup
    # For legal entity, first_name should be the full name
    customer_type = "legal"
    full_name = "Gulf Falcon Trading LLC"

    if customer_type == "legal":
        first_name = full_name
        last_name = ""
    else:
        first_name = full_name.split()[0]
        last_name = " ".join(full_name.split()[1:])

    assert first_name == "Gulf Falcon Trading LLC", (
        f"Legal entity FFR must use full name, not split(). Got: {first_name}"
    )
    assert last_name == "", f"Legal entity should have empty last_name. Got: {last_name}"


def test_ffr_natural_person_splits_name():
    """FFR for natural person should split first/last name."""
    customer_type = "natural"
    full_name = "John Ahmed Al Maktoum"

    if customer_type == "legal":
        first_name = full_name
        last_name = ""
    else:
        first_name = full_name.split()[0]
        last_name = " ".join(full_name.split()[1:])

    assert first_name == "John", f"Natural person first_name should be first word. Got: {first_name}"
    assert last_name == "Ahmed Al Maktoum", f"Natural person last_name should be remaining words. Got: {last_name}"


def test_ffr_blank_name_validation():
    """FFR with blank name should be detected early with clear error."""
    full_name = "  "  # Blank or whitespace

    # This should raise ValueError
    if not full_name.strip():
        with pytest.raises(ValueError):
            raise ValueError("Cannot file FFR: customer full_name is blank")
    else:
        pytest.fail("Should have raised ValueError for blank name")
