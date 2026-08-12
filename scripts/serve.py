"""Start the amlkit web interface.

    python scripts/serve.py

Binds to 127.0.0.1 by default, which is not reachable from the network. That is
the security boundary: there is no authentication, so anything else would expose
customer personal data to whoever can reach the host.

Environment:
    AMLKIT_BIND_HOST            default 127.0.0.1 (changing it prints a warning)
    AMLKIT_PORT                 default 8000
    AMLKIT_DB                   override database path
    AMLKIT_SINGLE_OPERATOR_MODE 1 if the firm has one compliance officer
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

from amlkit.api.deps import BIND_HOST, BIND_PORT, db_path, startup_warning  # noqa: E402
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
    conn.close()

    print(f"amlkit  ->  http://{BIND_HOST}:{BIND_PORT}")
    print(f"database: {db_path()}")

    if not rows:
        print("\nNo sanctions data loaded. Run:  python scripts/refresh.py\n")
    else:
        for r in rows:
            flag = "BREACH >24h" if r["breach"] else "current"
            print(f"  {r['key']:24} {r['entities']:>6} entities  [{flag}]")
        if any(r["breach"] for r in rows):
            print("\n  Mandatory lists are stale. Run:  python scripts/refresh.py\n")

    if single_operator_mode():
        print("\n  Single-operator mode ON: dismissals of sanctions and")
        print("  proliferation matches are recorded as having had no")
        print("  independent review.\n")

    uvicorn.run("amlkit.api.app:app", host=BIND_HOST, port=BIND_PORT, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
