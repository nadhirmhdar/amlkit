"""Delete quotation requests past the retention period (cases.applications.RETENTION_DAYS).

The scheduled /system/refresh call already does this; run this by hand to
purge on demand:  python scripts/purge_applications.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.cases.applications import RETENTION_DAYS, purge_expired  # noqa: E402
from amlkit.db import connect  # noqa: E402


def main() -> int:
    conn = connect(os.environ.get("AMLKIT_DB", "data/aml.db"))
    try:
        n = purge_expired(conn, actor="cli")
    finally:
        conn.close()
    print(f"Deleted {n} quotation request(s) idle for more than {RETENTION_DAYS} days.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
