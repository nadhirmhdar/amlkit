"""BigQuery GDELT GKG adverse media screening.

Queries the GDELT Global Knowledge Graph (GKG) table in BigQuery for
entity-level news intelligence — themes, tone, source counts — as a
complement to the article-level GDELT DOC 2.0 search in adverse_media.py.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class GdeltBqResult:
    status: str
    theme_counts: dict[str, int] = field(default_factory=dict)
    avg_tone: float = 0.0
    article_count: int = 0
    sample_sources: list[str] = field(default_factory=list)
    sample_headlines: list[str] = field(default_factory=list)


def _sanitize_name(name: str) -> str:
    """Keep only letters, digits, spaces, hyphens, and Arabic characters."""
    return re.sub(r"[^a-zA-Z0-9\s؀-ۿ\-]", "", name).strip()


def _make_bq_client(project: str):
    """Create a BigQuery client. Separated for testability."""
    from google.cloud import bigquery
    return bigquery.Client(project=project)


class GdeltBqScreener:

    def __init__(self, client_factory=None):
        self._client_factory = client_factory or _make_bq_client

    def screen(self, name: str, window_days: int = 90) -> GdeltBqResult:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            return GdeltBqResult(status="unconfigured")

        safe_name = _sanitize_name(name)
        if not safe_name:
            return GdeltBqResult(status="ok")

        try:
            client = self._client_factory(project)
        except Exception as exc:
            log.warning("BigQuery client init failed: %s", exc)
            return GdeltBqResult(status="unavailable")

        query = f"""
            SELECT V2Themes, V2Tone, SourceCommonName, DocumentIdentifier
            FROM `bigquery-public-data.gdelt_v2.gkg_partitioned`
            WHERE DATE(_PARTITIONTIME) >= DATE_SUB(CURRENT_DATE(), INTERVAL {int(window_days)} DAY)
              AND V2Persons LIKE '%{safe_name}%'
            ORDER BY DATE(_PARTITIONTIME) DESC
            LIMIT 100
        """

        try:
            rows = list(client.query(query).result())
        except Exception as exc:
            log.warning("BigQuery GDELT query failed: %s", exc)
            return GdeltBqResult(status="unavailable")

        if not rows:
            return GdeltBqResult(status="ok")

        theme_counter: Counter[str] = Counter()
        tones: list[float] = []
        sources: list[str] = []
        headlines: list[str] = []

        for row in rows:
            themes_raw = getattr(row, "V2Themes", "") or ""
            for theme in themes_raw.split(";"):
                theme = theme.strip()
                if theme:
                    theme_counter[theme] += 1

            tone_raw = getattr(row, "V2Tone", "") or ""
            if tone_raw:
                try:
                    tones.append(float(tone_raw.split(",")[0]))
                except (ValueError, IndexError):
                    pass

            source = getattr(row, "SourceCommonName", "") or ""
            if source and source not in sources:
                sources.append(source)

            url = getattr(row, "DocumentIdentifier", "") or ""
            if url and url not in headlines:
                headlines.append(url)

        avg_tone = sum(tones) / len(tones) if tones else 0.0

        return GdeltBqResult(
            status="ok",
            theme_counts=dict(theme_counter.most_common(20)),
            avg_tone=round(avg_tone, 2),
            article_count=len(rows),
            sample_sources=sources[:10],
            sample_headlines=headlines[:10],
        )
