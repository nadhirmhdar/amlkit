"""Minimal p21 compliance calendar smoke tests."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_routes_registered():
    """Smoke test: verify routes are registered."""
    from amlkit.api.app import app
    routes = [r.path for r in app.routes if hasattr(r, 'path')]
    assert "/compliance/calendar" in routes
    assert "/compliance/deadlines" in routes

def test_queries_exist():
    """Smoke test: verify query functions exist."""
    from amlkit import queries
    assert hasattr(queries, 'compliance_deadlines')
    assert hasattr(queries, 'compliance_deadline')

def test_template_exists():
    """Smoke test: verify template exists."""
    from pathlib import Path
    template = Path(__file__).parent.parent / "amlkit" / "web" / "templates" / "compliance_calendar.html"
    assert template.exists()
