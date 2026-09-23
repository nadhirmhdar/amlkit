"""Start the amlkit web interface.

    python scripts/serve.py

Binds to 127.0.0.1 by default -- not reachable from the network. Real login
now gates every action, but the deployment is still only as safe as its
transport: binding beyond loopback WITHOUT also configuring TLS sends
passwords and customer PII across the LAN in cleartext. See
AMLKIT_SSL_KEYFILE / AMLKIT_SSL_CERTFILE below, or put a TLS-terminating
reverse proxy (e.g. Caddy) in front instead.

Environment:
    AMLKIT_BIND_HOST            default 127.0.0.1 (changing it prints a warning)
    AMLKIT_PORT                 default 8000
    AMLKIT_DB                   override database path
    AMLKIT_SINGLE_OPERATOR_MODE 1 if a firm has one compliance officer
    AMLKIT_SSL_KEYFILE          path to a TLS private key, for LAN deployment
    AMLKIT_SSL_CERTFILE         path to the matching TLS certificate
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from amlkit.api.deps import (  # noqa: E402
    BIND_HOST,
    BIND_PORT,
    TLS_CONFIGURED,
    db_path,
    startup_warning,
)
from amlkit.cases.review import single_operator_mode  # noqa: E402
from amlkit.db import connect  # noqa: E402
from amlkit.ingest.loader import staleness_report  # noqa: E402


def main() -> int:
    warning = startup_warning()
    if warning:
        print("\n" + "!" * 72)
        print(warning)
        print("!" * 72 + "\n")

    conn = connect(db_path())
    rows = staleness_report(conn)
    org_count = conn.execute("SELECT COUNT(*) c FROM organizations").fetchone()["c"]
    conn.close()

    scheme = "https" if TLS_CONFIGURED else "http"
    print(f"amlkit  ->  {scheme}://{BIND_HOST}:{BIND_PORT}")
    print(f"database: {db_path()}")
    print(f"organizations: {org_count}"
          + (" -- register the first one at /register-organization" if org_count == 0 else ""))

    if not rows:
        print("\nNo sanctions data loaded. Run:  python scripts/refresh.py\n")
    else:
        for r in rows:
            flag = "BREACH >24h" if r["breach"] else "current"
            print(f"  {r['key']:24} {r['entities']:>6} entities  [{flag}]")
        if any(r["breach"] for r in rows):
            print("\n  Mandatory lists are stale. Run:  python scripts/refresh.py\n")

    # Issue #258: single_operator_mode is now per-org, not process-wide
    # Startup message removed; check per-org setting in admin UI instead
    if os.environ.get("AMLKIT_SINGLE_OPERATOR_MODE", "").strip().lower() in ("1", "true", "yes", "on"):
        print("\n  AMLKIT_SINGLE_OPERATOR_MODE env var set (instance default).")
        print("  Per-org config in DB takes precedence.\n")

    uvicorn.run(
        "amlkit.api.app:app", host=BIND_HOST, port=BIND_PORT, log_level="warning",
        ssl_keyfile=os.environ.get("AMLKIT_SSL_KEYFILE") or None,
        ssl_certfile=os.environ.get("AMLKIT_SSL_CERTFILE") or None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
