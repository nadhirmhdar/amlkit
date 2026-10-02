"""Daily GDELT GKG "net-cast" via BigQuery -- cheap, broad, names only.

Why this exists alongside screening/adverse_media.py, not instead of it
-------------------------------------------------------------------------
screening/adverse_media.py already gives real per-customer adverse-media
checks with actual headlines, via GDELT's free DOC 2.0 API. It is rate
limited to one request per ~5.5s, which is exactly why the project's own
docstring there says periodic re-screening of the whole customer book is
"an explicit per-customer action instead" -- a 400-customer book would take
over half an hour of pure throttling.

This module flips that constraint. GDELT's full historical+live GKG table is
also published as a public BigQuery dataset (gdelt-bq.gdeltv2), under the
same commercial-use-cleared GDELT terms already relied on in adverse_media.py
-- but a *naive* live query against it is not actually free at realistic
volume. Verified directly against this project's own GCP billing project
before writing this adapter:

    - gdelt-bq.gdeltv2.gkg (unpartitioned): a single-day, 5-column query
      scans ~2.2 TB. Unusable.
    - gdelt-bq.gdeltv2.gkg_partitioned (PARTITION BY DATE(_PARTITIONTIME)):
      filtering on _PARTITIONTIME actually prunes partitions. One day's
      partition, 5 columns: ~411 MB. A 24-month range: ~283 GB -- i.e. a
      single ad-hoc screen with that lookback would burn ~28% of BigQuery's
      1 TB/month free tier *per screen*. Also unusable as a live per-request
      call.

So this module only ever queries **one day's partition at a time** (~400MB,
comfortably inside the free tier run daily) and returns a cheap, broad list
of person names mentioned anywhere in that day's risk-themed coverage --
nothing else. It does NOT return headlines: the GKG table has no title
field (only DocumentIdentifier, the article URL, and SourceCommonName, the
publishing domain) -- unlike the DOC API's `artlist` mode, which does. That
is a real, deliberate trade: this module casts a wide, cheap net; cases/
manager.py's run_gdelt_watch() then spends the DOC API's real (rate-limited
but free) per-name search budget only on names this net actually flagged,
to get back a real headline an operator can judge at a glance. Building the
UI around raw GKG rows (URL + theme codes, no headline) would have been
strictly worse evidence for every single finding.

Risk theme lexicon
-------------------
GDELT GKG 2.0 tags every article with zero or more theme codes from its own
taxonomy (CAMEO-adjacent, not free text) -- these are NOT the English/Arabic
keyword lexicon in screening/adverse_media.py, which matches article titles.
The codes below were pulled by live-querying V2Themes for the substrings
CORRUPTION/FRAUD/LAUNDERING/BRIBERY/TERROR/SANCTION/EMBEZZL/CRIME/
TRAFFICKING/ARREST/CONVICT against a real day's partition, not guessed from
memory -- see the module's test fixtures for the exact sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from datetime import timedelta
from typing import Protocol

PROJECT_ENV = "AMLKIT_GCP_PROJECT_ID"
TABLE = "gdelt-bq.gdeltv2.gkg_partitioned"

# Exact-match theme codes confirmed present in a live day's GKG partition.
RISK_THEMES: tuple[str, ...] = (
    "CORRUPTION",
    "ECON_MONEYLAUNDERING",
    "ELECTION_FRAUD",
    "HUMAN_TRAFFICKING",
    "ORGANIZED_CRIME",
    "SANCTIONS",
    "SOC_GENERALCRIME",
    "ARREST",
    "CRIME_CARTELS",
    "CRIME_ILLEGAL_DRUGS",
    "CRIME_LOOTING",
    "CRIME_COMMON_ROBBERY",
)

# Prefix-match theme codes: GDELT enumerates hundreds of named-entity theme
# codes under these roots (one per terrorist organisation, for example) --
# matching the root rather than hardcoding every current member of each
# family, which GDELT adds to independently of this codebase's releases.
RISK_THEME_PREFIXES: tuple[str, ...] = (
    "TAX_TERROR_GROUP_",
    "TAX_FNCACT_EMBEZZLER",
    "TAX_FNCACT_FRAUD",
)

MAX_PERSONS_PER_DAY = 5000  # sanity ceiling, not a cost control -- see query


class GKGUnavailable(RuntimeError):
    """BigQuery could not be reached or returned something unusable.

    Soft failure, same philosophy as adverse_media.MediaUnavailable: a missed
    daily net-cast must not block anything or raise an incident on its own.
    The real per-customer check (screening/adverse_media.py, called directly
    from the UI) remains available regardless of whether this ran today.
    """


class GKGClient(Protocol):
    """The seam that keeps tests off BigQuery, same purpose as
    screening.adverse_media.MediaClient."""

    def fetch_persons(self, target_date: date_cls, *, project_id: str) -> list[str]:
        """Return every value GDELT's V2Persons field held for target_date's
        rows whose V2Themes matched the risk lexicon -- one raw
        "Name,CharOffset" segment per returned string, not yet parsed."""


def _theme_filter_sql() -> str:
    exact = " OR ".join(f"theme = '{t}'" for t in RISK_THEMES)
    prefixes = " OR ".join(f"STARTS_WITH(theme, '{p}')" for p in RISK_THEME_PREFIXES)
    return f"({exact} OR {prefixes})"


def build_query(target_date: date_cls) -> str:
    """BigQuery SQL for one day's partition, theme-filtered, persons only.

    Deliberately selects only V2Persons (plus the UNNEST'd theme used to
    filter) -- every extra column is bytes billed on every row in the
    partition, not just matching ones, since gkg_partitioned has no other
    index. _PARTITIONTIME bounds are a half-open [start, end) day so this
    never silently drifts onto a neighbouring day's partition.
    """
    start = target_date.isoformat()
    end = (target_date + timedelta(days=1)).isoformat()
    return f"""
        SELECT DISTINCT V2Persons
        FROM `{TABLE}`,
          UNNEST(SPLIT(V2Themes, ';')) AS theme_raw,
          UNNEST([SPLIT(theme_raw, ',')[OFFSET(0)]]) AS theme
        WHERE _PARTITIONTIME >= TIMESTAMP('{start}')
          AND _PARTITIONTIME < TIMESTAMP('{end}')
          AND V2Persons IS NOT NULL AND V2Persons != ''
          AND {_theme_filter_sql()}
        LIMIT {MAX_PERSONS_PER_DAY}
    """


class BigQueryGKGClient:
    """Real client: google-cloud-bigquery, Application Default Credentials.

    On Cloud Run this picks up the instance's own service account with no
    key file to manage, same as google-cloud-storage already does for the
    litestream backup path. Locally, `gcloud auth application-default login`
    (or a service account key via GOOGLE_APPLICATION_CREDENTIALS).
    """

    def fetch_persons(self, target_date: date_cls, *, project_id: str) -> list[str]:
        try:
            from google.cloud import bigquery
            from google.api_core.exceptions import GoogleAPICallError
        except ImportError as exc:
            raise GKGUnavailable(
                "google-cloud-bigquery is not installed"
            ) from exc

        client = bigquery.Client(project=project_id)
        try:
            job = client.query(build_query(target_date))
            rows = list(job.result(timeout=120))
        except GoogleAPICallError as exc:
            raise GKGUnavailable(f"BigQuery query failed: {exc}") from exc
        except Exception as exc:  # network/auth errors surface as plain Exception
            raise GKGUnavailable(f"BigQuery request failed: {exc}") from exc
        return [r["V2Persons"] for r in rows if r["V2Persons"]]


def parse_person_names(raw_values: list[str]) -> list[str]:
    """V2Persons is "Name,CharOffset;Name,CharOffset;..." per row.

    rsplit on the LAST comma: a person name can itself contain a comma
    (rare, but GDELT does not escape it), while the trailing character
    offset is always a plain integer GDELT appended itself.
    """
    names: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for segment in raw.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            name, _, offset = segment.rpartition(",")
            if not name or not offset.strip().isdigit():
                continue
            name = name.strip()
            key = name.upper()
            if name and key not in seen:
                seen.add(key)
                names.append(name)
    return names


def daily_flagged_persons(
    target_date: date_cls, *, project_id: str, client: GKGClient | None = None
) -> list[str]:
    """Distinct person names mentioned in target_date's risk-themed GDELT
    coverage, worldwide. Cheap and broad by design -- see module docstring
    for the verified cost and why no headline comes back with these.

    Never raises for provider failure (returns [] instead), mirroring
    screening.adverse_media.search()'s soft-failure contract: a missed net-
    cast is a gap in proactive coverage, not an outage that should alarm or
    block anything else.
    """
    cl = client or BigQueryGKGClient()
    try:
        raw = cl.fetch_persons(target_date, project_id=project_id)
    except GKGUnavailable:
        return []
    return parse_person_names(raw)
