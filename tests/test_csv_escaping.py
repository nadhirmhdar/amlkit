"""CSV formula injection protection tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.api.csv_utils import _escape_csv_formula  # noqa: E402


class TestCsvFormulaEscaping:
    def test_escapes_equals_sign(self) -> None:
        assert _escape_csv_formula("=SUM(1+1)") == "'=SUM(1+1)"

    def test_escapes_plus_sign(self) -> None:
        assert _escape_csv_formula("+1+1") == "'+1+1"

    def test_escapes_minus_sign(self) -> None:
        assert _escape_csv_formula("-1-1") == "'-1-1"

    def test_escapes_at_sign(self) -> None:
        assert _escape_csv_formula("@A1") == "'@A1"

    def test_escapes_tab(self) -> None:
        assert _escape_csv_formula("\tformula") == "'\tformula"

    def test_escapes_carriage_return(self) -> None:
        assert _escape_csv_formula("\rformula") == "'\rformula"

    def test_does_not_escape_safe_strings(self) -> None:
        assert _escape_csv_formula("Ahmed Al Mansoori") == "Ahmed Al Mansoori"
        assert _escape_csv_formula("ABC Corp") == "ABC Corp"
        assert _escape_csv_formula("123456") == "123456"

    def test_handles_none(self) -> None:
        assert _escape_csv_formula(None) is None

    def test_handles_numbers(self) -> None:
        assert _escape_csv_formula(42) == "42"
        # Negative numbers start with -, which is a formula injection risk, so they get escaped
        assert _escape_csv_formula(-5) == "'-5"
        assert _escape_csv_formula(0) == "0"

    def test_empty_string_not_escaped(self) -> None:
        assert _escape_csv_formula("") == ""

    def test_formula_in_middle_not_escaped(self) -> None:
        """Only escape if dangerous char is at the START of the cell."""
        assert _escape_csv_formula("Name =SUM") == "Name =SUM"
        assert _escape_csv_formula("Email@example.com") == "Email@example.com"
