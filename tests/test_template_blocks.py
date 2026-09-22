"""Template-block and stylesheet regression tests.

Background (UX lane finding #1, QA-12/QA-19 in
docs/reviews/2026-09-21-deployed-site-review/): base.html renders
``{% block body %}``, but three templates declared ``{% block content %}``,
so Jinja silently dropped their entire page body and the Freeze Obligations
and KYT rule-configuration pages rendered as nav + footer only. The same
review found those templates and the dashboard's freeze panel referencing
CSS classes that app.css never defined.

These tests pin both: every template that extends base.html must fill the
block base.html actually renders, and every class the freeze UI relies on
must have a selector in the shared stylesheet.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Reuse test_api's client fixture: a fresh org, signed in as its MLRO.
from test_api import client  # noqa: E402,F401

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "amlkit" / "web" / "templates"
APP_CSS = ROOT / "amlkit" / "web" / "static" / "app.css"

_EXTENDS_BASE = re.compile(r"""{%-?\s*extends\s+["']base\.html["']\s*-?%}""")
_BLOCK = re.compile(r"{%-?\s*block\s+(\w+)\s*-?%}")


def _templates_extending_base() -> list[Path]:
    return sorted(
        p for p in TEMPLATES.rglob("*.html")
        if _EXTENDS_BASE.search(p.read_text(encoding="utf-8"))
    )


def _rel(p: Path) -> str:
    return p.relative_to(TEMPLATES).as_posix()


# --------------------------------------------------------------- block names


def test_base_renders_block_body() -> None:
    """The contract every child template is checked against below."""
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "{% block body %}" in base
    assert "{% block content %}" not in base


@pytest.mark.parametrize(
    "template", _templates_extending_base(), ids=lambda p: _rel(p),
)
def test_child_template_fills_block_body_not_content(template: Path) -> None:
    """A child of base.html must define ``block body`` and never ``block
    content``. Jinja does not error on an unknown block name -- it just
    drops the content -- so this is the only place the mismatch surfaces."""
    blocks = set(_BLOCK.findall(template.read_text(encoding="utf-8")))
    assert "body" in blocks, (
        f"{_rel(template)} extends base.html but never defines "
        "{% block body %}; its page body will render blank"
    )
    assert "content" not in blocks, (
        f"{_rel(template)} defines {{% block content %}}, which base.html "
        "never renders"
    )


def test_all_three_previously_blank_templates_are_covered() -> None:
    """Guard the parametrize above against a rename of the offending files."""
    covered = {_rel(p) for p in _templates_extending_base()}
    for name in (
        "freeze_obligations.html",
        "freeze_obligation_detail.html",
        "admin/rule-config.html",
    ):
        assert name in covered, f"{name} no longer extends base.html?"


# ------------------------------------------------------------ page rendering


def test_freeze_obligations_page_renders_heading_and_empty_state(client) -> None:
    """GET /freeze-obligations as an MLRO on a fresh org: the page body is
    present (an <h1>) and, with no obligations yet, says so instead of
    rendering a bare table header."""
    r = client.get("/freeze-obligations")
    assert r.status_code == 200
    assert re.search(r"<h1[^>]*>\s*TFS Freeze Obligations\s*</h1>", r.text), r.text[:800]
    assert "No freeze obligations" in r.text


def test_rule_config_page_renders_heading_and_form(client) -> None:
    """GET /admin/rule-config as an MLRO: the page body is present (an <h1>)
    and the form is rendered with its submit control."""
    r = client.get("/admin/rule-config")
    assert r.status_code == 200
    assert re.search(r"<h1[^>]*>\s*Transaction Monitoring Rules\s*</h1>", r.text), r.text[:800]
    assert 'name="large_cash_threshold_aed"' in r.text
    assert "Update Configuration" in r.text


# ----------------------------------------------------------------- stylesheet

# Classes the freeze templates and the dashboard freeze panel rely on. Each
# must have a selector in app.css; a class that nothing styles is a silent
# UX regression (unstyled chips, invisible status colouring, doubled markers).
FREEZE_UI_CLASSES = [
    # dashboard.html <details> panel
    "freeze-obligations-panel",
    "freeze-obligations-summary",
    "freeze-obligations-title",
    "freeze-obligations-chevron",
    "freeze-obligations-content",
    "stat-chip",
    # freeze_obligations.html
    "alert-info",
    "stats-bar",
    "filter-form",
    "freeze-obligations-table",
    "badge",
    "badge-critical",
    "badge-high",
    "btn-sm",
    "status-pending_execution",
    "status-executed_pending_report",
    "status-reported",
    "status-resolved",
    "overdue",
    # freeze_obligation_detail.html
    "obligation-header",
    "timeline",
    "timeline-item",
    "actions",
    "btn-primary",
    "btn-secondary",
]


@pytest.mark.parametrize("cls", FREEZE_UI_CLASSES)
def test_freeze_ui_class_has_a_selector_in_app_css(cls: str) -> None:
    css = APP_CSS.read_text(encoding="utf-8")
    assert re.search(rf"\.{re.escape(cls)}(?![\w-])", css), (
        f".{cls} is used by the freeze UI but app.css has no selector for it"
    )


def test_freeze_summary_does_not_double_the_disclosure_marker() -> None:
    """The dashboard <summary> carries its own chevron span, so the
    browser's native ▶/▼ marker must be suppressed or the user sees two."""
    css = APP_CSS.read_text(encoding="utf-8")
    assert re.search(
        r"\.freeze-obligations-summary\s*{[^}]*list-style:\s*none", css
    ), "native list-style marker not suppressed on .freeze-obligations-summary"
    assert re.search(
        r"\.freeze-obligations-summary::-webkit-details-marker\s*{[^}]*display:\s*none", css
    ), "WebKit details marker not suppressed on .freeze-obligations-summary"


def test_freeze_list_template_has_no_inline_style_block() -> None:
    """Status row colours live in app.css (token-based), not in a per-page
    <style> block with hard-coded hex values."""
    src = (TEMPLATES / "freeze_obligations.html").read_text(encoding="utf-8")
    assert "<style" not in src
