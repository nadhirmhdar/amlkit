"""Shared CSV helpers used by both the web app (app.py) and mobile API (mobile.py)."""

from __future__ import annotations


def _escape_csv_formula(value):
    """Escape cells starting with formula injection characters.

    Prefixes cells starting with =, +, -, @, tab, or carriage return with a
    single quote to prevent Excel/LibreOffice from interpreting them as formulas.
    This is the standard mitigation for CSV formula injection (also known as
    CSV injection or formula injection).
    """
    if value is None:
        return None
    s = str(value)
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s
    return s
