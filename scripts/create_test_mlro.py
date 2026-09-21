#!/usr/bin/env python3
"""Create a test MLRO operator for an existing organization.

Usage:
    python scripts/create_test_mlro.py [--db-path PATH] [--org-slug SLUG] [--email EMAIL] [--name NAME]

Creates a test MLRO user with:
- Email: mlro@test-firm.local (or custom via --email)
- Password: TestMLRO2026!
- Role: mlro
- Email already verified (ready to log in immediately)

If --org-slug is omitted, finds the first active organization or creates "Test Firm".
"""

import sys
from pathlib import Path

# Ensure amlkit package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.db import connect, utcnow, DB_PATH
from amlkit.auth import hash_password
import argparse


def create_test_mlro(db_path: str | None = None, org_slug: str | None = None,
                     email: str | None = None, name: str | None = None) -> dict:
    """Create a test MLRO operator.

    Returns:
        dict with keys: email, password, org_name, org_slug, operator_id
    """
    conn = connect(db_path or DB_PATH)

    # Find or create test organization
    if org_slug:
        org_row = conn.execute(
            "SELECT id, name, slug FROM organizations WHERE slug=? AND status='active'",
            (org_slug,)
        ).fetchone()
        if not org_row:
            conn.close()
            raise ValueError(f"No active organization with slug '{org_slug}'")
    else:
        # Try to find an existing active org
        org_row = conn.execute(
            "SELECT id, name, slug FROM organizations WHERE status='active' LIMIT 1"
        ).fetchone()

        if not org_row:
            # Create Test Firm if no org exists
            print("No active organization found. Creating 'Test Firm'...")
            cursor = conn.execute(
                "INSERT INTO organizations (name, slug, status, created_at) VALUES (?,?,?,?) RETURNING id, name, slug",
                ("Test Firm", "test-firm", "active", utcnow())
            )
            org_row = cursor.fetchone()
            conn.commit()

    org_id = org_row["id"]
    org_name = org_row["name"]
    org_slug = org_row["slug"]

    # Define test MLRO credentials
    email = email or "mlro@test-firm.local"
    password = "TestMLRO2026!"
    name = name or "Test MLRO"

    # Check if operator already exists
    existing = conn.execute(
        "SELECT id, email FROM operators WHERE email=?", (email,)
    ).fetchone()

    if existing:
        conn.close()
        raise ValueError(f"Operator with email '{email}' already exists (id={existing['id']})")

    # Create the operator with email already verified
    now = utcnow()
    cursor = conn.execute(
        """INSERT INTO operators (org_id, name, email, password_hash, role, is_active,
                                   email_verified_at, failed_login_count, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           RETURNING id""",
        (org_id, name, email, hash_password(password), "mlro", 1, now, 0, now)
    )
    operator_id = cursor.fetchone()["id"]
    conn.commit()
    conn.close()

    return {
        "email": email,
        "password": password,
        "org_name": org_name,
        "org_slug": org_slug,
        "operator_id": operator_id,
    }


def main():
    parser = argparse.ArgumentParser(description="Create a test MLRO operator")
    parser.add_argument("--db-path", help="Path to SQLite database (default: data/aml.db)")
    parser.add_argument("--org-slug", help="Organization slug (default: find first active org)")
    parser.add_argument("--email", help="Email address (default: mlro@test-firm.local)")
    parser.add_argument("--name", help="Operator name (default: Test MLRO)")
    args = parser.parse_args()

    try:
        result = create_test_mlro(args.db_path, args.org_slug, args.email, args.name)

        print("\n[SUCCESS] Test MLRO operator created successfully!\n")
        print(f"  Organization: {result['org_name']} ({result['org_slug']})")
        print(f"  Operator ID:  {result['operator_id']}")
        print(f"  Email:        {result['email']}")
        print(f"  Password:     {result['password']}")
        print(f"  Role:         mlro")
        print(f"  Status:       Active, email verified")
        print("\nYou can now log in at /login with these credentials.")

    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
