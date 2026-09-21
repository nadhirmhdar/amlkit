"""Test for STR Builder org name pre-population (fix/163).

The STR Builder form should pre-populate the reporting entity name with the
logged-in org's name from session.org_name, not fall back to a hardcoded default.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the client fixture from test_api
pytest_plugins = ["tests.test_api"]


def test_str_builder_prepopulates_org_name(client) -> None:
    """STR Builder form must pre-populate reporting entity with logged-in org name."""
    # The test_api client fixture creates org "Test Firm"
    # Create a customer to build report for
    r = client.post("/customers", data={
        "reference": "C-STR-163",
        "full_name": "Test Customer",
        "customer_type": "natural",
        "csrf_token": _csrf(client),
    })
    assert r.status_code in (200, 303), "Customer creation failed"

    # GET the STR builder form
    r = client.get("/reports/build?customer_id=1&report_type=STR")
    assert r.status_code == 200, "STR builder route failed"

    # Form should contain org name "Test Firm", NOT hardcoded "Grovisor Business Consultants"
    assert "Test Firm" in r.text, \
        "STR Builder form should pre-populate with logged-in org name 'Test Firm'"

    assert "Grovisor Business Consultants" not in r.text, \
        "STR Builder form should NOT fall back to hardcoded default 'Grovisor Business Consultants'"


def _csrf(client):
    """Extract CSRF token from a page."""
    r = client.get("/")
    if 'name="csrf_token" value="' not in r.text:
        return "test-token"
    start = r.text.index('name="csrf_token" value="') + len('name="csrf_token" value="')
    end = r.text.index('"', start)
    return r.text[start:end]
