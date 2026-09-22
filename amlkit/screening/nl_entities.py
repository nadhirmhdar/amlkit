"""Cloud Natural Language entity-sentiment client.

Used by screening/media_pipeline.py stage 2 (entity resolution) to score
whether a candidate article's headline is actually *about* the screened
customer, via per-entity salience, and to record the sentiment attached to
that entity mention.

Deliberately sent only the title + snippet the acquisition stage already has
in hand (from GDELT's artlist or Vertex AI Search's result snippet) --
NEVER a scraped article body. `screening/adverse_media.py` already commits
this codebase to never fetching article pages (their text is the publisher's
copyright, and a full fetch would be a much larger surface to redact PII
from); Cloud Natural Language billing is also per-document, so sending a
one-paragraph snippet instead of a full page is both the safer and the
cheaper choice.

Off by default (AMLKIT_NL_ENABLED=0): when off, `media_pipeline.py` falls
back to the existing keyword/name-evidence logic in `adverse_media.py`
rather than skipping entity resolution outright.

Pinned against google-cloud-language 2.21.0 (the `language_v1` module,
`LanguageServiceClient.analyze_entity_sentiment`). Uses Application Default
Credentials -- no API key, consistent with running as a Cloud Run service
account (see module docstring pattern in screening/gdelt_bq.py).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("amlkit.screening.nl_entities")

# Cloud NL enforces its own request size cap; this is a local, conservative
# cap so a pathological snippet does not blow the API's own limit and turn
# into an opaque 400 the pipeline has to guess about.
MAX_TEXT_LEN = 4000


@dataclass
class EntityMention:
    name: str
    type_: str
    salience: float
    sentiment_score: float = 0.0
    sentiment_magnitude: float = 0.0
    # Knowledge Graph MID, when Cloud NL's metadata includes one for this
    # entity. Not guaranteed -- NL only attaches a `mid` for entities it can
    # confidently resolve against the public Knowledge Graph.
    mid: str | None = None


@dataclass
class NlResult:
    status: str  # disabled | unconfigured | ok | unavailable
    entities: list[EntityMention] = field(default_factory=list)


def _make_client():
    from google.cloud import language_v1

    return language_v1.LanguageServiceClient()


class NaturalLanguageScreener:
    """Thin DI wrapper so tests never construct a real LanguageServiceClient."""

    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory or _make_client

    def analyze(self, text: str) -> NlResult:
        if os.environ.get("AMLKIT_NL_ENABLED", "0") != "1":
            return NlResult(status="disabled")

        text = (text or "").strip()[:MAX_TEXT_LEN]
        if not text:
            return NlResult(status="ok")

        try:
            client = self._client_factory()
        except Exception:
            log.warning("Cloud Natural Language client init failed", exc_info=True)
            return NlResult(status="unavailable")

        from google.cloud import language_v1

        document = language_v1.Document(
            content=text, type_=language_v1.Document.Type.PLAIN_TEXT
        )
        try:
            response = client.analyze_entity_sentiment(
                document=document, encoding_type=language_v1.EncodingType.UTF8
            )
        except Exception:
            log.warning("Cloud Natural Language request failed", exc_info=True)
            return NlResult(status="unavailable")

        entities: list[EntityMention] = []
        for ent in getattr(response, "entities", []) or []:
            metadata = dict(getattr(ent, "metadata", None) or {})
            sentiment = getattr(ent, "sentiment", None)
            type_ = getattr(ent, "type_", None)
            entities.append(
                EntityMention(
                    name=getattr(ent, "name", "") or "",
                    type_=getattr(type_, "name", None) or str(type_ or ""),
                    salience=float(getattr(ent, "salience", 0.0) or 0.0),
                    sentiment_score=float(getattr(sentiment, "score", 0.0) or 0.0)
                    if sentiment is not None
                    else 0.0,
                    sentiment_magnitude=float(getattr(sentiment, "magnitude", 0.0) or 0.0)
                    if sentiment is not None
                    else 0.0,
                    mid=metadata.get("mid"),
                )
            )

        return NlResult(status="ok", entities=entities)
