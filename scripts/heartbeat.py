"""Lightweight connectivity check for all sanctions sources.

Verifies that every configured upstream sanctions feed is reachable by
calling each adapter's fetch() method.  This is a "smoke test" — it
downloads but does not parse or store, so it is safe to run frequently
(e.g. every 15 minutes from a monitoring cron).

Exit codes:
    0  all mandatory sources responded successfully
    1  at least one mandatory source failed
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest.base import AdapterError  # noqa: E402
from amlkit.ingest.eocn import uae_local_terrorists  # noqa: E402
from amlkit.ingest.cia import cia_world_leaders  # noqa: E402
from amlkit.ingest.un import UNSanctionsAdapter  # noqa: E402
from amlkit.ingest.ofac import OFACSDNAdapter  # noqa: E402
from amlkit.ingest.eu import EUSanctionsAdapter  # noqa: E402
from amlkit.ingest.uk import UKSanctionsAdapter  # noqa: E402

# THE canonical list of every upstream this deployment screens against, as
# adapter factories. This is the single source of truth for "which sources do
# we check": both this connectivity heartbeat AND the daily drift canary
# (.github/workflows/source-canary.yml, `sources` job) iterate THIS list.
# Keeping one hand-maintained copy is deliberate — a second inline copy in the
# canary had already drifted (it omitted EU), silently dropping a source from
# coverage, which is the exact failure the canary exists to prevent. Whether
# each source blocks the build is decided per-adapter via `is_mandatory`, so it
# too has one source of truth (the adapter) rather than a hardcoded list.
ALL_SOURCES = [
    uae_local_terrorists,
    UNSanctionsAdapter,
    OFACSDNAdapter,
    EUSanctionsAdapter,
    UKSanctionsAdapter,
    cia_world_leaders,
]


def heartbeat(sources=None) -> int:
    """Run connectivity checks; return 0 (all mandatory OK) or 1 (failure)."""
    if sources is None:
        sources = ALL_SOURCES

    mandatory_failed: list[str] = []

    print("=" * 60)
    print("Heartbeat — sanctions source connectivity check")
    print("=" * 60)

    for factory in sources:
        adapter = factory()
        name = adapter.key
        mandatory = adapter.is_mandatory
        tag = "mandatory" if mandatory else "optional "

        try:
            t0 = time.monotonic()
            adapter.fetch()
            elapsed = time.monotonic() - t0
            print(f"  OK    [{tag}] {name} ({elapsed:.1f}s)")
        except (AdapterError, Exception) as exc:
            print(f"  FAIL  [{tag}] {name}: {exc}", file=sys.stderr)
            if mandatory:
                mandatory_failed.append(name)

    print()
    if mandatory_failed:
        print(
            f"RESULT: FAIL — {len(mandatory_failed)} mandatory source(s) unreachable: "
            + ", ".join(mandatory_failed)
        )
        return 1

    print("RESULT: OK — all mandatory sources reachable")
    return 0


def main() -> None:
    sys.exit(heartbeat())


if __name__ == "__main__":
    main()
