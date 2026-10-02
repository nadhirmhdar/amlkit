"""Wikidata ministers/cabinet-level PEPs -- direct ingestion.

WHY THIS ADAPTER EXISTS
-----------------------
Same reason as `eocn.py` and `cia.py`: OpenSanctions already publishes a PEP
dataset built substantially from Wikidata (its own docs name Wikidata as a
primary PEP feed), but under CC-BY-NC -- free for non-commercial use only,
with no exemption for commercial users. Wikidata's own content, by contrast,
is CC0 (public domain dedication) straight from the primary source, which
removes the licence constraint entirely rather than inheriting it through an
aggregator -- the same move `eocn.py`'s docstring explains for the UAE list.

WHAT THIS IS AND IS NOT
------------------------
This covers people who have held a position that is a Wikidata subclass of
"minister" (Q83307) with no end date, or an end date on or after 1995 --
i.e. current and recent-former cabinet-level officials, across every country
Wikidata has structured data for. Verified live against the real endpoint
before writing this adapter: ~38,000 people meet that definition today.

It does NOT cover heads of state (CIA World Leaders already does, see
cia.py), national legislators, judges, or central bank governors -- all of
which UAE CDD obligations also reach, and none of which this adapter claims
to provide. Baseline cabinet-level coverage, same honest framing as cia.py:
a firm relying on this plus cia.py has broader but still partial PEP
coverage, not comprehensive.

TWO-PHASE FETCH, AND WHY
-------------------------
A single query joining `SERVICE wikibase:label` across this many rows, or
adding `ORDER BY` so OFFSET-based pagination is stable, reliably times out
on Wikidata's public endpoint -- confirmed live: an ORDER BY + LIMIT 2000
OFFSET 20000 page timed out past 60s. The same statement-only query with NO
label service and NO ORDER BY returns the full ~38k rows without timing out.

So phase 1 fetches (person QID, position QID, country QID, start, end)
tuples, unordered, paginated by LIMIT/OFFSET -- accepting that Wikidata's
internal row order could in principle drift between two paginated calls
(it's live data, not a frozen snapshot), which could skip or duplicate a
handful of rows across a page boundary. For a periodic bulk refresh this is
an acceptable trade, not a silent one: documented here rather than assumed
away. Phase 2 resolves the distinct QIDs collected in phase 1 to English
labels in small batches via a VALUES clause -- the standard, scale-safe
alternative to SERVICE wikibase:label for bulk Wikidata extraction.
"""

from __future__ import annotations

from typing import Iterator

import httpx

from .base import AdapterError, SourceEntity

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"

# Q83307 = "minister" (government). wdt:P279* walks the subclass hierarchy,
# so this also catches country-specific minister subclasses (e.g. "Minister
# of Economy of Belarus") without enumerating every country's variant.
POSITION_ROOT = "wd:Q83307"

# Recent-former cutoff. A position held entirely before this date is not
# included; one still open (no P582 end-time qualifier) always is. See
# module docstring for the live-verified row count this produces.
SINCE_YEAR = "1995"

PAGE_SIZE = 2000
LABEL_BATCH_SIZE = 400
MAX_PAGES = 100  # ~200k rows ceiling -- a circuit breaker, not an expected count


def _statement_query(limit: int, offset: int) -> str:
    return f"""
        SELECT ?person ?position ?country ?start ?end WHERE {{
          ?person p:P39 ?stmt .
          ?stmt ps:P39 ?position .
          ?position wdt:P279* {POSITION_ROOT} .
          OPTIONAL {{ ?position wdt:P1001 ?country }}
          OPTIONAL {{ ?stmt pq:P580 ?start }}
          OPTIONAL {{ ?stmt pq:P582 ?end }}
          FILTER(!BOUND(?end) || ?end >= "{SINCE_YEAR}-01-01"^^xsd:dateTime)
        }}
        LIMIT {limit} OFFSET {offset}
    """


def _label_query(qids: list[str]) -> str:
    values = " ".join(f"wd:{q}" for q in qids)
    return f"""
        SELECT ?id ?label WHERE {{
          VALUES ?id {{ {values} }}
          ?id rdfs:label ?label .
          FILTER(LANG(?label) = "en")
        }}
    """


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


class WikidataPEPAdapter:
    """Ministers/cabinet-level PEPs, direct from Wikidata's own endpoint."""

    def __init__(self) -> None:
        self.key = "wikidata_ministers"
        self.title = "Wikidata Ministers (PEPs)"
        self.publisher = "Wikidata"
        self.source_url = "https://www.wikidata.org/wiki/Wikidata:WikiProject_Politicians"
        # CC0 (public domain dedication) -- Wikidata's own content licence,
        # the primary source OpenSanctions' wd_peps dataset itself draws
        # from. Free to redistribute commercially with no licence held over
        # it at all, unlike going through that aggregator.
        self.licence = "CC0 1.0 (public domain dedication)"
        self.is_mandatory = False

    # -- fetch --------------------------------------------------------------

    def fetch(self) -> bytes:
        import json

        with httpx.Client(timeout=90, headers={
            "User-Agent": USER_AGENT, "Accept": "application/sparql-results+json",
        }) as client:
            rows = self._fetch_statements(client)
            if not rows:
                raise AdapterError(
                    f"{self.key}: query returned 0 position-holder rows - "
                    "endpoint or query shape may have changed"
                )

            qids = sorted({q for row in rows for q in row[:3] if q})
            labels = self._fetch_labels(client, qids)

        documents = [
            json.dumps(
                {
                    "person": p, "person_label": labels.get(p, ""),
                    "position": pos, "position_label": labels.get(pos, ""),
                    "country": c, "country_label": labels.get(c, "") if c else "",
                    "start": start, "end": end,
                },
                ensure_ascii=False,
            ).encode("utf-8")
            for p, pos, c, start, end in rows
        ]
        return b"\n".join(documents)

    def _fetch_statements(self, client: httpx.Client) -> list[tuple[str, str, str | None, str | None, str | None]]:
        rows: list[tuple[str, str, str | None, str | None, str | None]] = []
        for page in range(MAX_PAGES):
            offset = page * PAGE_SIZE
            try:
                r = client.get(ENDPOINT, params={"query": _statement_query(PAGE_SIZE, offset), "format": "json"})
                r.raise_for_status()
                bindings = r.json()["results"]["bindings"]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise AdapterError(f"{self.key}: statement query failed at offset {offset} - {exc}") from exc

            if not bindings:
                break
            for b in bindings:
                person = _qid(b["person"]["value"])
                position = _qid(b["position"]["value"])
                country = _qid(b["country"]["value"]) if "country" in b else None
                start = b.get("start", {}).get("value")
                end = b.get("end", {}).get("value")
                rows.append((person, position, country, start, end))
        return rows

    def _fetch_labels(self, client: httpx.Client, qids: list[str]) -> dict[str, str]:
        labels: dict[str, str] = {}
        for i in range(0, len(qids), LABEL_BATCH_SIZE):
            batch = qids[i:i + LABEL_BATCH_SIZE]
            try:
                r = client.get(ENDPOINT, params={"query": _label_query(batch), "format": "json"})
                r.raise_for_status()
                bindings = r.json()["results"]["bindings"]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                # Non-fatal: a handful of unresolved labels fall back to the
                # bare QID in parse() rather than losing the whole batch's
                # entities over one transient label-service hiccup.
                continue
            for b in bindings:
                labels[_qid(b["id"]["value"])] = b["label"]["value"]
        return labels

    # -- parse ----------------------------------------------------------------

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        import json

        seen = 0
        for line in payload.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            name = (row.get("person_label") or row.get("person") or "").strip()
            if not name:
                continue

            position_label = (row.get("position_label") or "").strip()
            country_label = (row.get("country_label") or "").strip()

            seen += 1
            yield SourceEntity(
                source_id=f"WD-{row['person']}",
                schema_type="Person",
                caption=name,
                names=[],
                countries=[country_label] if country_label else [],
                birth_date=None,  # not fetched -- see module docstring scope
                gender=None,
                topics=["role.pep"],
                programs=[],
                identifiers=[("wikidata", row["person"])],
                listed_at=row.get("start"),
                raw={
                    "source": "Wikidata",
                    "wikidata_id": row["person"],
                    "position": position_label or row.get("position"),
                    "position_qid": row.get("position"),
                    "country": country_label or None,
                    "start": row.get("start"),
                    "end": row.get("end"),
                },
            )

        if seen == 0:
            raise AdapterError(
                f"{self.key}: parsed 0 position-holders from the fetched payload"
            )


def wikidata_ministers() -> WikidataPEPAdapter:
    """Baseline cabinet-level PEP coverage, from Wikidata's own endpoint."""
    return WikidataPEPAdapter()
