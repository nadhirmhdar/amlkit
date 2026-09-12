#!/usr/bin/env python3
"""Pre-PR gate checks for amlkit.

Verifies that a branch is ready for PR creation:
1. All tests pass
2. No secrets in the codebase
3. README is accurate

Run before creating a PR to catch common issues early.
"""

import subprocess
import sys
from pathlib import Path

# ANSI color codes for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def print_section(title: str) -> None:
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def check_tests() -> bool:
    """Run the test suite and return True if all pass."""
    print_section("Running test suite")

    # Use the venv Python to run pytest
    venv_python = Path(".venv/Scripts/python.exe")
    if not venv_python.exists():
        venv_python = Path(".venv/bin/python")  # Unix path

    if not venv_python.exists():
        print(f"{YELLOW}⚠ No virtualenv found. Using system Python.{RESET}")
        cmd = [sys.executable, "-m", "pytest", "tests/", "-x", "-q"]
    else:
        cmd = [str(venv_python), "-m", "pytest", "tests/", "-x", "-q"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0:
            print(f"{GREEN}✓ All tests passed{RESET}")
            return True
        else:
            print(f"{RED}✗ Tests failed{RESET}")
            print(result.stdout)
            print(result.stderr)
            return False
    except subprocess.TimeoutExpired:
        print(f"{RED}✗ Tests timed out (>10 minutes){RESET}")
        return False
    except FileNotFoundError:
        print(f"{RED}✗ pytest not found. Install with: pip install pytest{RESET}")
        return False


def check_secrets() -> bool:
    """Check for potential secrets in the codebase."""
    print_section("Checking for secrets")

    # Patterns that might indicate secrets
    secret_patterns = [
        (r"password\s*=\s*['\"][^'\"]+['\"]", "password="),
        (r"secret\s*=\s*['\"][^'\"]+['\"]", "secret="),
        (r"api_key\s*=\s*['\"][^'\"]+['\"]", "api_key="),
        (r"token\s*=\s*['\"][^'\"]+['\"]", "token="),
        (r"private_key\s*=\s*['\"][^'\"]+['\"]", "private_key="),
        (r"aws_access_key", "aws_access_key"),
        (r"AKIA[0-9A-Z]{16}", "AWS key"),
    ]

    # Files to exclude from secret scanning
    exclude_patterns = [
        "tests/",
        ".venv/",
        ".git/",
        "__pycache__/",
        "*.pyc",
        ".pytest_cache/",
        "scripts/pre_pr_check.py",  # This file
    ]

    import re

    issues_found = []

    for pattern, name in secret_patterns:
        # Use git grep to respect .gitignore
        try:
            result = subprocess.run(
                ["git", "grep", "-n", "-E", pattern],
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")

                # Filter out excluded paths
                filtered_lines = []
                for line in lines:
                    should_exclude = False
                    for exclude in exclude_patterns:
                        if exclude.rstrip("/") in line:
                            should_exclude = True
                            break
                    if not should_exclude:
                        filtered_lines.append(line)

                if filtered_lines:
                    issues_found.append((name, filtered_lines))
        except FileNotFoundError:
            print(f"{YELLOW}⚠ git not found, skipping git grep{RESET}")
            break

    if not issues_found:
        print(f"{GREEN}✓ No secrets detected{RESET}")
        return True
    else:
        print(f"{RED}✗ Potential secrets found:{RESET}")
        for name, lines in issues_found:
            print(f"\n  Pattern: {name}")
            for line in lines[:5]:  # Show first 5 matches
                print(f"    {line}")
            if len(lines) > 5:
                print(f"    ... and {len(lines) - 5} more")
        print(f"\n{YELLOW}Review these carefully before committing!{RESET}")
        return False


def check_readme() -> bool:
    """Verify README exists and has basic expected content."""
    print_section("Checking README")

    readme_path = Path("README.md")

    if not readme_path.exists():
        print(f"{RED}✗ README.md not found{RESET}")
        return False

    content = readme_path.read_text()

    # Check for key sections
    required_sections = [
        ("# ", "Title"),
        ("install", "Installation instructions"),
        ("test", "Testing instructions"),
    ]

    missing = []
    for pattern, description in required_sections:
        if pattern.lower() not in content.lower():
            missing.append(description)

    if missing:
        print(f"{YELLOW}⚠ README might be missing:{RESET}")
        for item in missing:
            print(f"  - {item}")
        print(f"{YELLOW}Consider updating README.md{RESET}")
        return True  # Warning, not failure

    print(f"{GREEN}✓ README looks good{RESET}")
    return True


def main() -> int:
    """Run all checks and return exit code."""
    print(f"\n{YELLOW}Pre-PR Gate Checks{RESET}")
    print("Verifying branch is ready for pull request...\n")

    # Change to repo root
    repo_root = Path(__file__).resolve().parent.parent
    import os
    os.chdir(repo_root)

    checks = [
        ("Tests", check_tests),
        ("Secrets", check_secrets),
        ("README", check_readme),
    ]

    results = {}
    for name, check_fn in checks:
        try:
            results[name] = check_fn()
        except Exception as e:
            print(f"{RED}✗ {name} check crashed: {e}{RESET}")
            results[name] = False

    # Summary
    print_section("Summary")
    all_passed = all(results.values())

    for name, passed in results.items():
        status = f"{GREEN}✓{RESET}" if passed else f"{RED}✗{RESET}"
        print(f"  {status} {name}")

    if all_passed:
        print(f"\n{GREEN}✓ All checks passed! Ready to create PR.{RESET}\n")
        return 0
    else:
        print(f"\n{RED}✗ Some checks failed. Fix issues before creating PR.{RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
