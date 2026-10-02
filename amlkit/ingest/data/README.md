# Wikidata PEP snapshot

`wikidata_peps.jsonl.gz` and `wikidata_peps.meta.json` (not present until the first run) are a
snapshot of Wikidata's ministers and cabinet-level position-holders. Wikidata content is CC0, so
it may be committed. The adapter (`amlkit/ingest/wikidata_peps.py`) loads it in place of live
queries, which Wikimedia blocks from many cloud and CI addresses.

Refresh monthly from an ordinary network:

    python scripts/snapshot_wikidata_peps.py
    git add amlkit/ingest/data && git commit -m "Refresh Wikidata PEP snapshot"

A snapshot older than 62 days (`AMLKIT_WIKIDATA_SNAPSHOT_MAX_AGE_DAYS`) is refused by the adapter.
