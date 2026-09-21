"""Google Knowledge Graph PEP/public-figure disambiguation.

Uses the Knowledge Graph Search API to resolve a name to structured entity
metadata — types (Person, Organization), description, Wikipedia/Wikidata IDs —
useful for automated PEP disambiguation ("Is this Vijay Mallya the Indian
tycoon?").
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

log = logging.getLogger("amlkit.screening.knowledge_graph")

ENDPOINT = "https://kgsearch.googleapis.com/v1/entities:search"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"


@dataclass
class KgEntity:
    name: str
    types: list[str] = field(default_factory=list)
    description: str | None = None
    detailed_description: str | None = None
    wikipedia_url: str | None = None
    kg_id: str | None = None
    score: float = 0.0


@dataclass
class KgResult:
    status: str
    entities: list[KgEntity] = field(default_factory=list)


class KnowledgeGraphScreener:
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def _resolve_key(self) -> str | None:
        return self._api_key or os.environ.get("GOOGLE_KG_API_KEY")

    def screen(
        self, name: str, types: list[str] | None = None
    ) -> KgResult:
        key = self._resolve_key()
        if not key:
            return KgResult(status="unconfigured")

        url = f"{ENDPOINT}?query={name}&key={key}&limit=5&languages=en"
        if types:
            url += f"&types={','.join(types)}"

        try:
            resp = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=15.0,
            )
            resp.raise_for_status()
        except Exception:
            log.warning("Knowledge Graph API request failed for %r", name, exc_info=True)
            return KgResult(status="unavailable")

        data = resp.json()
        entities: list[KgEntity] = []
        for item in data.get("itemListElement", []):
            result = item.get("result", {})
            detailed = result.get("detailedDescription", {})
            entities.append(
                KgEntity(
                    name=result.get("name", ""),
                    types=[t for t in result.get("@type", []) if t != "Thing"],
                    description=result.get("description"),
                    detailed_description=detailed.get("articleBody"),
                    wikipedia_url=detailed.get("url"),
                    kg_id=result.get("@id"),
                    score=item.get("resultScore", 0.0),
                )
            )

        return KgResult(status="ok", entities=entities)
