#!/usr/bin/env python3
"""Tenant-isolation security scanner for amlkit.

Statically checks code for common tenant-isolation violations:
1. Query functions missing org_id parameter
2. POST routes missing CSRF validation
3. Routes accessing tenant data without session checks
4. SQL queries on org-scoped tables missing org_id in WHERE clause
5. Write operations using org_id from fetched rows instead of session

Run before creating PRs to catch tenant-isolation bugs early.
"""

import ast
import re
import sys
from pathlib import Path
from typing import Any

# ANSI color codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# Org-scoped tables that must include org_id in WHERE clauses
ORG_SCOPED_TABLES = {
    "customers",
    "screenings",
    "alerts",
    "alert_reviews",
    "risk_assessments",
    "documents",
    "reports",
    "audit_log",
    "ubo_links",
    "transaction_alerts",
}

# Shared tables that should NOT require org_id
SHARED_TABLES = {
    "entities",
    "datasets",
    "entity_names",
    "name_tokens",
    "entity_identifiers",
}


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def check_queries_org_id(file_path: str) -> list[dict[str, Any]]:
    """Check that query functions in queries.py take org_id parameter.

    Args:
        file_path: Path to Python file to check

    Returns:
        List of violations, each with: function, line, message
    """
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=file_path)
    except (FileNotFoundError, SyntaxError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # Get parameter names
        param_names = [arg.arg for arg in node.args.args]

        # Check if function queries org-scoped data
        # Heuristic: if function body contains queries to org-scoped tables,
        # it should have org_id parameter
        func_source = ast.get_source_segment(open(file_path).read(), node)
        if not func_source:
            continue

        # Check if function queries org-scoped tables
        queries_org_data = False
        for table in ORG_SCOPED_TABLES:
            if f"FROM {table}" in func_source or f"from {table}" in func_source:
                queries_org_data = True
                break

        # If queries org-scoped data but lacks org_id parameter, flag it
        if queries_org_data and "org_id" not in param_names:
            violations.append({
                "function": node.name,
                "line": node.lineno,
                "message": f"Function queries org-scoped data but missing 'org_id' parameter",
                "file": file_path,
            })

    return violations


def check_post_csrf(file_path: str) -> list[dict[str, Any]]:
    """Check that POST routes validate CSRF tokens.

    Args:
        file_path: Path to Python file to check

    Returns:
        List of violations
    """
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content, filename=file_path)
    except (FileNotFoundError, SyntaxError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # Check if function has @app.post decorator
        has_post_decorator = False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if hasattr(decorator.func, 'attr') and decorator.func.attr == 'post':
                    has_post_decorator = True
                    break
            elif isinstance(decorator, ast.Attribute):
                if decorator.attr == 'post':
                    has_post_decorator = True
                    break

        if not has_post_decorator:
            continue

        # Check if function actually calls require_csrf or has csrf_token parameter
        # Look for actual function calls, not comments
        has_csrf_check = False

        # Check parameters for csrf_token
        param_names = [arg.arg for arg in node.args.args]
        if "csrf_token" in param_names:
            has_csrf_check = True

        # Check for require_csrf call in AST (not just string matching)
        if not has_csrf_check:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    # Check for require_csrf() call
                    if isinstance(child.func, ast.Name) and child.func.id == "require_csrf":
                        has_csrf_check = True
                        break
                    # Check for Depends(require_csrf) pattern
                    if isinstance(child.func, ast.Name) and child.func.id == "Depends":
                        if child.args and isinstance(child.args[0], ast.Name):
                            if child.args[0].id == "require_csrf":
                                has_csrf_check = True
                                break

        if not has_csrf_check:
            violations.append({
                "function": node.name,
                "line": node.lineno,
                "message": "POST route missing CSRF validation (require_csrf)",
                "file": file_path,
            })

    return violations


def check_session_requirement(file_path: str) -> list[dict[str, Any]]:
    """Check that routes accessing tenant data require session.

    Args:
        file_path: Path to Python file to check

    Returns:
        List of violations
    """
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content, filename=file_path)
    except (FileNotFoundError, SyntaxError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        # Check if it's a route handler (has @app.get/@app.post decorator)
        is_route = False
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if hasattr(decorator.func, 'attr') and decorator.func.attr in ('get', 'post', 'put', 'delete'):
                    is_route = True
                    break

        if not is_route:
            continue

        func_source = ast.get_source_segment(content, node) or ""

        # Check if route accesses tenant data (mentions org-scoped tables)
        accesses_tenant_data = any(
            table in func_source for table in ORG_SCOPED_TABLES
        )

        # Skip public endpoints (health checks, static assets)
        if not accesses_tenant_data or "/health" in func_source or node.name == "health_check":
            continue

        # Check if function validates session using AST (not string matching)
        has_session_check = False

        # Look for actual function calls to require_session or current_session
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                # Check for require_session() or current_session()
                if isinstance(child.func, ast.Name):
                    if child.func.id in ("require_session", "current_session"):
                        has_session_check = True
                        break
            # Check for session assignment: session = ...
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name) and target.id == "session":
                        has_session_check = True
                        break

        if not has_session_check:
            violations.append({
                "function": node.name,
                "line": node.lineno,
                "message": "Route accesses tenant data without session validation",
                "file": file_path,
            })

    return violations


def check_sql_where_clauses(file_path: str) -> list[dict[str, Any]]:
    """Check SQL queries on org-scoped tables include org_id in WHERE.

    Args:
        file_path: Path to Python file to check

    Returns:
        List of violations
    """
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content, filename=file_path)
    except (FileNotFoundError, SyntaxError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        func_source = ast.get_source_segment(content, node) or ""

        # Find SQL queries in the function
        # Look for UPDATE, DELETE, SELECT on org-scoped tables
        sql_pattern = r'(UPDATE|DELETE\s+FROM|SELECT\s+.*?\s+FROM)\s+(\w+)'
        matches = re.finditer(sql_pattern, func_source, re.IGNORECASE)

        for match in matches:
            operation = match.group(1).upper()
            table = match.group(2)

            # Skip shared tables
            if table in SHARED_TABLES:
                continue

            # Check if this is an org-scoped table
            if table not in ORG_SCOPED_TABLES:
                continue

            # Extract the SQL statement (rough heuristic)
            sql_start = match.start()
            # Find the end of the SQL statement (look for closing quote)
            sql_end = func_source.find('"', sql_start + 50)
            if sql_end == -1:
                sql_end = func_source.find("'", sql_start + 50)
            if sql_end == -1:
                sql_end = min(sql_start + 200, len(func_source))

            sql_statement = func_source[sql_start:sql_end]

            # Check if org_id appears in WHERE clause
            if "WHERE" in sql_statement.upper():
                if "org_id" not in sql_statement:
                    violations.append({
                        "function": node.name,
                        "line": node.lineno,
                        "message": f"{operation} on '{table}' missing org_id in WHERE clause",
                        "file": file_path,
                    })
            else:
                # No WHERE clause at all on org-scoped table
                if "UPDATE" in operation or "DELETE" in operation:
                    violations.append({
                        "function": node.name,
                        "line": node.lineno,
                        "message": f"{operation} on '{table}' has no WHERE clause (should include org_id)",
                        "file": file_path,
                    })

    return violations


def check_session_vs_fetched_org_id(file_path: str) -> list[dict[str, Any]]:
    """Check that write operations use session org_id, not fetched org_id.

    Args:
        file_path: Path to Python file to check

    Returns:
        List of violations
    """
    violations = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            tree = ast.parse(content, filename=file_path)
    except (FileNotFoundError, SyntaxError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        func_source = ast.get_source_segment(content, node) or ""

        # Heuristic: look for pattern of fetching org_id from SELECT
        # then using it in UPDATE/INSERT/DELETE
        has_select_org_id = re.search(r'SELECT\s+.*?org_id.*?FROM', func_source, re.IGNORECASE)
        has_write_with_org_id = re.search(r'(UPDATE|INSERT|DELETE).*?org_id', func_source, re.IGNORECASE)

        if has_select_org_id and has_write_with_org_id:
            # Check if org_id comes from row access (suspicious pattern)
            if re.search(r'row\["org_id"\]|row\[\'org_id\'\]', func_source):
                violations.append({
                    "function": node.name,
                    "line": node.lineno,
                    "message": "Write operation uses org_id from fetched row (should use session.org_id)",
                    "file": file_path,
                })

    return violations


def scan_file(file_path: Path) -> dict[str, list[dict]]:
    """Run all checks on a single file.

    Returns:
        Dict mapping check name to list of violations
    """
    return {
        "queries_org_id": check_queries_org_id(str(file_path)),
        "post_csrf": check_post_csrf(str(file_path)),
        "session_requirement": check_session_requirement(str(file_path)),
        "sql_where_clauses": check_sql_where_clauses(str(file_path)),
        "session_vs_fetched": check_session_vs_fetched_org_id(str(file_path)),
    }


def main() -> int:
    """Run all security checks and return exit code."""
    print(f"\n{YELLOW}Tenant-Isolation Security Scanner{RESET}")
    print("Checking for common tenant-isolation violations...\n")

    # Determine files to scan
    if len(sys.argv) > 1:
        # Scan specific file(s)
        files_to_scan = [Path(arg) for arg in sys.argv[1:]]
    else:
        # Scan main codebase files
        repo_root = Path(__file__).parent.parent
        files_to_scan = [
            repo_root / "amlkit" / "queries.py",
            repo_root / "amlkit" / "api" / "app.py",
            repo_root / "amlkit" / "cases" / "manager.py",
            repo_root / "amlkit" / "cases" / "review.py",
        ]

    all_violations = []

    for file_path in files_to_scan:
        if not file_path.exists():
            continue

        results = scan_file(file_path)

        for check_name, violations in results.items():
            for violation in violations:
                all_violations.append({
                    "check": check_name,
                    **violation,
                })

    # Report results
    if not all_violations:
        print(f"{GREEN}OK No tenant-isolation violations found{RESET}")
        return 0

    print(f"{RED}X Found {len(all_violations)} violation(s):{RESET}\n")

    for violation in all_violations:
        print(f"{RED}  {violation['file']}:{violation['line']}: {violation['function']}(){RESET}")
        print(f"    {violation['message']}")
        print()

    print(f"{RED}Fix these violations before creating a PR.{RESET}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
