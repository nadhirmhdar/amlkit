"""Vertex AI Search (Discovery Engine) adapter for regional/UAE press search.

Why Vertex AI Search and not Google's Custom Search JSON API
--------------------------------------------------------------
The obvious tool for "search a curated set of news domains" is Custom Search
JSON API (the old `customsearch.cse.list` + a Programmable Search Engine).
It is not used here because it is closed to new customers and Google has
published an end-of-life date: "As of ... the Custom Search JSON API is
closed to new sign ups ... The API will be turned down on January 1, 2027."
(https://developers.google.com/custom-search/v1/overview, checked while
building this module). Building a new integration against an API that is
already closed to new customers and has an announced shutdown date one
release cycle away would be shipping technical debt on day one.

Vertex AI Search (part of the Discovery Engine API) is the supported
replacement direction: a human creates a **data store** scoped to specific
UAE/regional news domains (via the Discovery Engine console or
`gcloud discovery-engine` -- see the PR description for the exact human-only
steps) and this module queries that data store's serving config with
Application Default Credentials. No API key, no deprecated product.

Package pinned: google-cloud-discoveryengine 0.20.4, `discoveryengine_v1`
namespace, `SearchServiceClient.search()`. Checked against the installed
package's own signatures rather than assumed -- see requirements.txt.

Off by default (AMLKIT_VAIS_ENABLED=0). When on, `AMLKIT_VAIS_ENGINE_ID`
accepts either a bare engine/data-store ID (the common case -- this module
builds the full serving-config resource path) or an already-fully-qualified
serving config resource name (starting with "projects/"), for a human who
already knows the exact serving config they want and would rather not rely
on this module's path-building convention.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("amlkit.screening.vertex_search")

# Discovery Engine enforces its own ceiling on page_size; capped locally so a
# misconfigured caller gets a clear local value instead of an API 400.
MAX_RESULTS = 50


@dataclass
class VaisArticle:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass
class VaisResult:
    status: str  # disabled | unconfigured | ok | unavailable
    articles: list[VaisArticle] = field(default_factory=list)


def _make_client():
    from google.cloud import discoveryengine_v1 as discoveryengine

    return discoveryengine.SearchServiceClient()


def serving_config_path(project: str, location: str, engine_id: str) -> str:
    """Build (or pass through) the serving config resource name.

    `engine_id` may already be a full resource path (a human who configured
    the data store themselves and wants to name the exact serving config);
    otherwise this assumes the default search app / default serving config
    convention Discovery Engine creates for a new Vertex AI Search app.
    """
    engine_id = (engine_id or "").strip()
    if engine_id.startswith("projects/"):
        return engine_id
    return (
        f"projects/{project}/locations/{location}/collections/default_collection"
        f"/engines/{engine_id}/servingConfigs/default_search"
    )


class VertexAiSearchScreener:
    """Thin DI wrapper so tests never construct a real SearchServiceClient."""

    def __init__(self, client_factory=None) -> None:
        self._client_factory = client_factory or _make_client

    def search(self, query: str, *, max_results: int = 10) -> VaisResult:
        if os.environ.get("AMLKIT_VAIS_ENABLED", "0") != "1":
            return VaisResult(status="disabled")

        project = os.environ.get("AMLKIT_VAIS_PROJECT")
        engine_id = os.environ.get("AMLKIT_VAIS_ENGINE_ID")
        if not project or not engine_id:
            return VaisResult(status="unconfigured")

        query = (query or "").strip()
        if not query:
            return VaisResult(status="ok")

        location = os.environ.get("AMLKIT_VAIS_LOCATION", "global")

        try:
            client = self._client_factory()
        except Exception:
            log.warning("Vertex AI Search client init failed", exc_info=True)
            return VaisResult(status="unavailable")

        from google.cloud import discoveryengine_v1 as discoveryengine

        request = discoveryengine.SearchRequest(
            serving_config=serving_config_path(project, location, engine_id),
            query=query,
            page_size=max(1, min(int(max_results), MAX_RESULTS)),
        )

        try:
            pager = client.search(request)
        except Exception:
            log.warning("Vertex AI Search query failed", exc_info=True)
            return VaisResult(status="unavailable")

        articles: list[VaisArticle] = []
        try:
            for result in pager:
                doc = getattr(result, "document", None)
                data = {}
                if doc is not None:
                    struct = getattr(doc, "derived_struct_data", None)
                    if struct:
                        data = dict(struct)
                url = (data.get("link") or "").strip()
                if not url:
                    continue
                title = data.get("title") or ""
                snippet = ""
                snippets = data.get("snippets") or []
                if isinstance(snippets, list) and snippets:
                    first = snippets[0]
                    if isinstance(first, dict):
                        snippet = first.get("snippet", "") or ""
                articles.append(VaisArticle(url=url, title=title, snippet=snippet))
        except Exception:
            log.warning("Vertex AI Search result parsing failed", exc_info=True)
            return VaisResult(status="unavailable")

        return VaisResult(status="ok", articles=articles)
