"""Every real HTML <table> with more than two columns must be wrapped in
<div class="table-responsive"> (app.css: overflow-x: auto, plus a mobile
edge-to-edge bleed at max-width:680px). Without it, a table wider than the
viewport is simply cut off with no way to reach the missing columns --
reported live on /freeze-obligations (8 columns) on a phone.

.table-responsive existed in app.css already but was never wired to a
single template before this fix -- these tests pin that it now is, on
every genuinely wide table, and stay a regression guard against a future
table being added without it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEMPLATES_DIR = Path(__file__).parent.parent / "amlkit" / "web" / "templates"
CSS_PATH = Path(__file__).parent.parent / "amlkit" / "web" / "static" / "app.css"


def _tables_and_wrap_state(html: str) -> list[tuple[str, bool]]:
    """For each <table ...> tag, return (its opening tag, whether the
    nearest preceding unclosed block-level ancestor is table-responsive).
    Walks backwards from each <table to see if a <div class="table-responsive">
    opened more recently than any intervening </div> closed it."""
    results = []
    for m in re.finditer(r"<table\b[^>]*>", html):
        before = html[: m.start()]
        last_wrapper_open = before.rfind('<div class="table-responsive">')
        # Anything that closed *after* the wrapper opened but *before* this
        # table means the wrapper was already shut again.
        closed_after_open = before.rfind("</div>", last_wrapper_open) if last_wrapper_open != -1 else -1
        wrapped = last_wrapper_open != -1 and closed_after_open <= last_wrapper_open
        results.append((m.group(), wrapped))
    return results


def test_table_responsive_class_exists_in_css() -> None:
    css = CSS_PATH.read_text(encoding="utf-8")
    assert re.search(r"\.table-responsive\s*\{[^}]*overflow-x\s*:\s*auto", css), \
        ".table-responsive must set overflow-x: auto"


def test_freeze_obligations_list_table_is_wrapped() -> None:
    html = (TEMPLATES_DIR / "freeze_obligations.html").read_text(encoding="utf-8")
    tables = _tables_and_wrap_state(html)
    assert tables, "expected the freeze obligations table"
    assert all(wrapped for _, wrapped in tables), tables


def test_freeze_obligation_detail_assets_table_is_wrapped() -> None:
    html = (TEMPLATES_DIR / "freeze_obligation_detail.html").read_text(encoding="utf-8")
    tables = _tables_and_wrap_state(html)
    assert tables, "expected the assets-frozen table"
    assert all(wrapped for _, wrapped in tables), tables


def test_evidence_multi_column_tables_are_wrapped() -> None:
    """evidence.html has both 2-column label/value tables (fine as-is, no
    header row, don't overflow) and real multi-column data grids (UBO,
    risk factors, screening record, four-eyes reviews) -- only the latter
    need the wrapper. Identify them by an actual <th> header row."""
    html = (TEMPLATES_DIR / "evidence.html").read_text(encoding="utf-8")
    tables = _tables_and_wrap_state(html)
    assert len(tables) >= 4, f"expected at least 4 tables in evidence.html, found {len(tables)}"
    # Every table containing a header <tr> with 3+ <th> cells is a data
    # grid at real overflow risk and must be wrapped.
    for block_match in re.finditer(r"<table\b[^>]*>.*?</table>", html, re.DOTALL):
        block = block_match.group()
        th_count = len(re.findall(r"<th\b", block))
        if th_count >= 3:
            before = html[: block_match.start()]
            last_wrapper_open = before.rfind('<div class="table-responsive">')
            closed_after_open = before.rfind("</div>", last_wrapper_open) if last_wrapper_open != -1 else -1
            wrapped = last_wrapper_open != -1 and closed_after_open <= last_wrapper_open
            assert wrapped, f"table with {th_count} header cells is not wrapped: {block[:120]}"
