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
A single query joining `SERVICE wikibase:label` across this many rows
reliably times out on Wikidata's public endpoint, so phase 1 fetches
(person QID, position QID, country QID, start, end) tuples with no label
service, and phase 2 resolves the distinct QIDs collected in phase 1 to
English labels in small batches via a VALUES clause -- the standard,
scale-safe alternative to SERVICE wikibase:label for bulk Wikidata
extraction.

Phase 1 is paginated by KEYSET, not OFFSET: `ORDER BY STR(?person) LIMIT n`
plus `FILTER(STR(?person) > "<last seen person IRI>")` for every page after
the first. This is deliberate, not incidental:

- `ORDER BY ?person LIMIT 2000 OFFSET 0` (ordering the raw IRI term) took
  ~29s live; `ORDER BY STR(?person)` (ordering the lexical string) took
  ~6s for the same page -- the server evidently has to do real work to
  compare IRIs as terms that it does not have to do to compare them as
  strings.
- OFFSET-based pagination got slower as the offset grew (a live OFFSET
  20000 page timed out past 60s), because the engine has to materialise
  and discard every row before the offset on every call. Keyset avoids
  that: filtering by "greater than the last value seen" cost ~6-9s
  whether it was page 1 or page 2, live-verified -- not growing with
  position, unlike OFFSET.
- OFFSET pagination with NO stable ORDER BY (the original design) was
  measured live to return only ~21% overlap between two otherwise-
  identical paginated calls -- Wikidata's internal row order is not
  guaranteed stable across requests at all, so skipped/duplicated rows
  were not "a handful", they were most of the dataset. `ORDER BY
  STR(?person)` plus a keyset filter fixes this: each page is a
  deterministic, non-overlapping slice of a stable sort order,
  live-verified across two consecutive pages (zero overlap, correct
  ordering, contiguous boundary).

The ORDER BY clause and the keyset FILTER both cast with the same STR()
deliberately -- `ORDER BY ?person` orders by IRI term, not by its lexical
string, so filtering with STR(?person) against an ORDER BY ?person sort
would compare pages sorted one way against a boundary computed the other
way, producing the same kind of silent gaps/overlaps this scheme exists to
avoid. Both sides of the keyset comparison must use the identical cast.
"""

from __future__ import annotations

import os

from typing import Iterator

import httpx

from .base import AdapterError, SourceEntity

ENDPOINT = "https://query.wikidata.org/sparql"
# Wikimedia's User-Agent policy asks every client for a name/version and a way
# to contact the operator (a URL or email). Override with
# AMLKIT_WIKIDATA_USER_AGENT if you run this under a different contact.
USER_AGENT = os.environ.get(
    "AMLKIT_WIKIDATA_USER_AGENT",
    "groAML/1.0 (https://groaml.grovisor.ae; info@grovisor.ae) python-httpx",
)

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


def _escape_iri(iri: str) -> str:
    """Escape a full IRI for use inside a double-quoted SPARQL string
    literal. Wikidata entity IRIs never legitimately contain a quote or
    backslash, but a keyset boundary value flows from a previous response
    back into the next request's query text, so it is escaped defensively
    rather than trusted."""
    return iri.replace("\\", "\\\\").replace('"', '\\"')


def _statement_query(limit: int, after: str | None) -> str:
    """`after`, when given, is the full person IRI (not the bare QID) of the
    last row returned by the previous page -- see the module docstring for
    why this is a keyset filter rather than OFFSET, and why both this filter
    and ORDER BY below cast through STR() identically.
    """
    keyset_filter = (
        f'FILTER(STR(?person) > "{_escape_iri(after)}")' if after is not None else ""
    )
    return f"""
        SELECT ?person ?position ?country ?start ?end WHERE {{
          ?person p:P39 ?stmt .
          ?stmt ps:P39 ?position .
          ?position wdt:P279* {POSITION_ROOT} .
          OPTIONAL {{ ?position wdt:P1001 ?country }}
          OPTIONAL {{ ?stmt pq:P580 ?start }}
          OPTIONAL {{ ?stmt pq:P582 ?end }}
          FILTER(!BOUND(?end) || ?end >= "{SINCE_YEAR}-01-01"^^xsd:dateTime)
          {keyset_filter}
        }}
        ORDER BY STR(?person)
        LIMIT {limit}
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


def _sparql_get(client: httpx.Client, query: str, *, max_attempts: int = 3) -> list[dict]:
    """Run one SPARQL query with exponential-backoff retry on transient
    errors. ingest/base.py's fetch_with_retry isn't reusable here: this
    adapter holds one shared httpx.Client across ~95-120 sequential calls
    (one per statement page / label batch) and needs parsed JSON bindings
    back, not a one-shot GET returning raw bytes. Without this, a single
    transient timeout among that many calls aborted the whole adapter run
    with zero records -- worth absorbing given the module's own docstring
    says this endpoint "reliably times out" under load.
    """
    import time

    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            r = client.get(ENDPOINT, params={"query": query, "format": "json"})
            if r.status_code == 403:
                # Wikimedia's robot-policy block ("Please respect our robot
                # policy"). It is applied per client IP, and retrying only
                # adds to the traffic that caused it -- fail fast and say why.
                raise AdapterError(
                    "Wikidata refused this client with HTTP 403 (Wikimedia robot policy, "
                    "applied per IP -- common from cloud and CI addresses). Retrying will "
                    "not help; contact bot-traffic@wikimedia.org to be allowed, or run the "
                    "refresh from an unblocked network. " + r.text[:120].strip()
                )
            r.raise_for_status()
            return r.json()["results"]["bindings"]
        except AdapterError:
            raise
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
    raise AdapterError(f"sparql query failed after {max_attempts} attempt(s) - {last_exc}") from last_exc


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
        after: str | None = None
        for page in range(MAX_PAGES):
            try:
                bindings = _sparql_get(client, _statement_query(PAGE_SIZE, after))
            except AdapterError as exc:
                raise AdapterError(f"{self.key}: statement query failed after page {page} - {exc}") from exc

            if not bindings:
                break
            for b in bindings:
                person_iri = b["person"]["value"]
                person = _qid(person_iri)
                position = _qid(b["position"]["value"])
                country = _qid(b["country"]["value"]) if "country" in b else None
                start = b.get("start", {}).get("value")
                end = b.get("end", {}).get("value")
                rows.append((person, position, country, start, end))
            # Keyset continuation: next page asks for STR(?person) greater
            # than the last row's full IRI. Rows are ORDER BY STR(?person)
            # (see _statement_query), so the last binding in this page is
            # the correct boundary for the next one.
            after = bindings[-1]["person"]["value"]
        return rows

    def _fetch_labels(self, client: httpx.Client, qids: list[str]) -> dict[str, str]:
        labels: dict[str, str] = {}
        for i in range(0, len(qids), LABEL_BATCH_SIZE):
            batch = qids[i:i + LABEL_BATCH_SIZE]
            try:
                bindings = _sparql_get(client, _label_query(batch))
            except AdapterError:
                # Non-fatal, even after retries: a handful of unresolved
                # labels fall back to the bare QID in parse() rather than
                # losing the whole batch's entities over this label lookup.
                continue
            for b in bindings:
                labels[_qid(b["id"]["value"])] = b["label"]["value"]
        return labels

    # -- parse ----------------------------------------------------------------

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        """One SourceEntity per PERSON, not per (person, position) row.

        A single person can hold more than one ministerial position (a
        Deputy PM who also holds a portfolio is not unusual) -- phase 1's
        query returns one row per position, so a person like that produces
        multiple rows here. Every row for the same person shares the same
        source_id (derived from the person QID), and entities.(dataset_id,
        source_id) is UNIQUE (see db.py) -- load() snapshots existing rows
        once before its insert/update loop, so yielding a second entity
        with a source_id already seen EARLIER IN THIS SAME BATCH hits a
        raw INSERT with no conflict handling and raises a bare
        sqlite3.IntegrityError, which none of this adapter's callers catch
        (they only catch AdapterError) -- aborting the scheduled refresh
        before the rest of that run's work (FATF table reload, every org's
        rescreen) happens. Grouping by person here is the fix: all of a
        person's positions collapse into one entity's raw["positions"].
        """
        import json
        from collections import OrderedDict

        by_person: "OrderedDict[str, dict]" = OrderedDict()
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

            person = row["person"]
            group = by_person.setdefault(person, {"name": name, "rows": []})
            group["rows"].append(row)

        seen = 0
        for person, group in by_person.items():
            rows = group["rows"]
            seen += 1

            countries: "OrderedDict[str, None]" = OrderedDict()
            positions = []
            starts = []
            for row in rows:
                position_label = (row.get("position_label") or "").strip()
                country_label = (row.get("country_label") or "").strip()
                if country_label:
                    countries.setdefault(country_label, None)
                positions.append({
                    "position": position_label or row.get("position"),
                    "position_qid": row.get("position"),
                    "country": country_label or None,
                    "start": row.get("start"),
                    "end": row.get("end"),
                })
                if row.get("start"):
                    starts.append(row["start"])

            # Earliest start across all of a person's positions, as a
            # conservative "PEP status began" marker -- ISO 8601 date
            # strings sort chronologically as plain strings.
            listed_at = min(starts) if starts else None

            yield SourceEntity(
                source_id=f"WD-{person}",
                schema_type="Person",
                caption=group["name"],
                names=[],
                countries=list(countries),
                birth_date=None,  # not fetched -- see module docstring scope
                gender=None,
                topics=["role.pep"],
                programs=[],
                identifiers=[("wikidata", person)],
                listed_at=listed_at,
                raw={
                    "source": "Wikidata",
                    "wikidata_id": person,
                    "positions": positions,
                },
            )

        if seen == 0:
            raise AdapterError(
                f"{self.key}: parsed 0 position-holders from the fetched payload"
            )


def wikidata_ministers() -> WikidataPEPAdapter:
    """Baseline cabinet-level PEP coverage, from Wikidata's own endpoint."""
    return WikidataPEPAdapter()
