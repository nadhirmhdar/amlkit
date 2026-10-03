"""Refresh the committed Wikidata PEP snapshot (monthly is sensible).

Wikimedia blocks many cloud and CI addresses from query.wikidata.org, so run
this from an ordinary network (a laptop, or a machine Wikimedia has allowed):

    python scripts/snapshot_wikidata_peps.py
    git add amlkit/ingest/data && git commit -m "Refresh Wikidata PEP snapshot"

It queries Wikidata once, writes amlkit/ingest/data/wikidata_peps.jsonl.gz and
wikidata_peps.meta.json, and refuses to replace a snapshot with one that is
much smaller (a truncated or blocked run) unless --force is given. Wikidata
content is CC0, so the snapshot may be committed.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest import wikidata_peps as w  # noqa: E402
from amlkit.ingest.base import AdapterError  # noqa: E402


def build_snapshot(out_dir: Path, *, force: bool = False, min_ratio: float = 0.5, payload: bytes | None = None) -> dict:
    """Write the snapshot (fetching live unless `payload` is given) and return its meta."""
    out_dir.mkdir(parents=True, exist_ok=True)
    data_file = out_dir / "wikidata_peps.jsonl.gz"
    meta_file = out_dir / "wikidata_peps.meta.json"

    if payload is None:
        payload = w.WikidataPEPAdapter().fetch_live()
    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    people = len({r["person"] for r in rows})
    if not rows or not people:
        raise AdapterError("query returned no rows; nothing written")

    if meta_file.exists() and not force:
        try:
            previous = json.loads(meta_file.read_text(encoding="utf-8")).get("rows", 0)
        except (OSError, ValueError):
            previous = 0
        if previous and len(rows) < previous * min_ratio:
            raise AdapterError(
                f"new snapshot has {len(rows)} rows, under {int(min_ratio * 100)}% of the current {previous}; "
                "looks truncated or blocked. Re-run, or pass --force if the drop is real."
            )

    # mtime=0 keeps the gzip bytes identical for identical data (clean diffs).
    data_file.write_bytes(gzip.compress(payload, mtime=0))
    meta = {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": len(rows),
        "people": people,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "source": "query.wikidata.org SPARQL (ministers, position-holders since " + w.SINCE_YEAR + ")",
        "licence": "CC0 1.0 (public domain dedication)",
        "user_agent": w.USER_AGENT,
    }
    meta_file.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", type=Path, default=w.SNAPSHOT_DIR)
    ap.add_argument("--force", action="store_true", help="replace the snapshot even if it shrinks sharply")
    args = ap.parse_args()
    try:
        meta = build_snapshot(args.out_dir, force=args.force)
    except AdapterError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {meta['rows']} rows / {meta['people']} people (as of {meta['as_of']}) to {args.out_dir}")
    print("Next: git add amlkit/ingest/data && git commit -m 'Refresh Wikidata PEP snapshot'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
