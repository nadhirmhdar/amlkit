"""Tests for tenant-isolation security scanner.

Tests verify that the scanner catches common tenant-isolation violations.
"""

import subprocess
from pathlib import Path

import pytest


def test_detects_missing_org_id_in_queries():
    """Scanner should catch query functions without org_id parameter."""
    from scripts.security_scan import check_queries_org_id

    fixture_path = Path(__file__).parent / "fixtures" / "bad_queries.py"
    violations = check_queries_org_id(str(fixture_path))

    # Should find 3 violations (get_customer_list, get_screening_results, get_alerts)
    assert len(violations) >= 3, f"Expected at least 3 violations, got {len(violations)}"

    # Check that violation messages mention org_id
    for violation in violations:
        assert "org_id" in violation["message"].lower(), \
            f"Violation message should mention 'org_id': {violation['message']}"

    # Verify specific functions are flagged
    flagged_functions = {v["function"] for v in violations}
    assert "get_customer_list" in flagged_functions
    assert "get_screening_results" in flagged_functions
    assert "get_alerts" in flagged_functions

    # Verify get_entities is NOT flagged (operates on shared data)
    assert "get_entities" not in flagged_functions, \
        "get_entities operates on shared 'entities' table and should not be flagged"


def test_detects_missing_csrf_in_post_routes():
    """Scanner should catch POST routes without CSRF validation."""
    from scripts.security_scan import check_post_csrf

    fixture_path = Path(__file__).parent / "fixtures" / "bad_routes.py"
    violations = check_post_csrf(str(fixture_path))

    # Should find 2 violations (create_customer_no_csrf, dispose_alert_no_csrf)
    assert len(violations) >= 2, f"Expected at least 2 violations, got {len(violations)}"

    # Check that violation messages mention CSRF
    for violation in violations:
        assert "csrf" in violation["message"].lower(), \
            f"Violation message should mention 'CSRF': {violation['message']}"

    # Verify specific routes are flagged
    flagged_routes = {v["function"] for v in violations}
    assert "create_customer_no_csrf" in flagged_routes
    assert "dispose_alert_no_csrf" in flagged_routes


def test_detects_missing_session_check():
    """Scanner should catch routes accessing tenant data without session."""
    from scripts.security_scan import check_session_requirement

    fixture_path = Path(__file__).parent / "fixtures" / "bad_routes.py"
    violations = check_session_requirement(str(fixture_path))

    # Should find list_reports_no_session
    assert len(violations) >= 1, f"Expected at least 1 violation, got {len(violations)}"

    # Verify health_check is NOT flagged (public endpoint)
    flagged_routes = {v["function"] for v in violations}
    assert "health_check" not in flagged_routes, \
        "health_check is a public endpoint and should not require session"


def test_detects_sql_without_org_id_in_where():
    """Scanner should catch SQL queries on org-scoped tables without org_id in WHERE."""
    from scripts.security_scan import check_sql_where_clauses

    fixture_path = Path(__file__).parent / "fixtures" / "bad_sql.py"
    violations = check_sql_where_clauses(str(fixture_path))

    # Should find 3 violations (UPDATE/DELETE/SELECT without org_id filter)
    assert len(violations) >= 3, f"Expected at least 3 violations, got {len(violations)}"

    # Verify specific functions are flagged
    flagged_functions = {v["function"] for v in violations}
    assert "update_customer_no_org_filter" in flagged_functions
    assert "delete_alert_no_org_filter" in flagged_functions
    assert "select_screenings_no_org_filter" in flagged_functions

    # Verify update_dataset_error is NOT flagged (operates on shared datasets table)
    assert "update_dataset_error" not in flagged_functions, \
        "update_dataset_error operates on shared 'datasets' table and should not be flagged"


def test_detects_fetched_org_id_in_writes():
    """Scanner should flag write operations using org_id from fetched rows."""
    from scripts.security_scan import check_session_vs_fetched_org_id

    fixture_path = Path(__file__).parent / "fixtures" / "bad_sql.py"
    violations = check_session_vs_fetched_org_id(str(fixture_path))

    # Should find use_fetched_org_id
    assert len(violations) >= 1, f"Expected at least 1 violation, got {len(violations)}"

    flagged_functions = {v["function"] for v in violations}
    assert "use_fetched_org_id" in flagged_functions


def test_scanner_cli_on_clean_codebase():
    """Scanner should run successfully and report any violations found.

    Note: The scanner may find real violations in the codebase - that's expected.
    This test just verifies the scanner runs without crashing.
    """
    result = subprocess.run(
        ["python", "scripts/security_scan.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    # Scanner should exit 0 (clean) or 1 (violations found), not crash
    assert result.returncode in (0, 1), \
        f"Scanner should exit 0 or 1, got {result.returncode}"

    # If violations found, output should contain violation details
    if result.returncode == 1:
        output = result.stdout + result.stderr
        assert "violation" in output.lower() or "missing" in output.lower(), \
            "Scanner output should report violations when exit code is 1"


def test_scanner_cli_on_violations():
    """Scanner should fail (exit 1) when violations are found."""
    result = subprocess.run(
        ["python", "scripts/security_scan.py", "tests/fixtures/bad_queries.py"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )

    assert result.returncode == 1, \
        "Scanner should exit 1 when violations are found"

    # Output should contain violation details
    output = result.stdout + result.stderr
    assert "violation" in output.lower() or "error" in output.lower(), \
        "Scanner output should report violations"
