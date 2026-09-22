"""Google Cloud adverse-media pipeline: acquisition -> resolution -> triage -> vault.

Implements the 4-stage architecture in the target diagram, mapped onto this
codebase's existing screening modules wherever one already exists, and three
new adapter modules where none did:

  1. Data Acquisition
       - BigQuery public dataset `gdelt-bq.gdeltv2.gkg`   -> screening/gdelt_bq.py (existing)
       - GDELT DOC 2.0 (global news, 65+ languages)        -> screening/adverse_media.py (existing)
       - targeted regional/UAE press search                -> screening/vertex_search.py (new)
  2. Entity Resolution
       - Knowledge Graph Search API (disambiguation, MIDs) -> screening/knowledge_graph.py (existing)
       - Cloud Natural Language (entity salience/sentiment) -> screening/nl_entities.py (new)
  3. Autonomous AI Triage
       - Vertex AI Gemini (translation + predicate-offence  -> ai/gemini.py (existing module,
         classification)                                       new triage_adverse_media())
  4. Audit Vault
       - amlkit's SQLite, trigger-locked audit trail         -> db.py (media_pipeline_runs /
                                                                  media_pipeline_articles) + audit()

This module is the orchestrator (`run_pipeline`) plus the acquisition/
resolution/triage glue; it does not talk to any Google API directly except
through the DI-friendly client classes named above, which is what makes
every stage independently fakeable in tests (see `PipelineClients`).

Design choices inherited from screening/adverse_media.py, deliberately kept:

  * Query-time, not ingested (there is no adverse-media "list" to snapshot).
  * Soft failure per source: one source being unreachable degrades the run
    (recorded in `errors`) rather than aborting it -- a compliance record
    that a source could not be reached is still evidence a check ran.
  * Findings are SUGGESTIONS. Nothing in this module ever writes a
    'relevant' or 'not_relevant' status, calls a risk reassessment, or
    otherwise treats a triaged article as a determination. An MLRO/officer
    must still work every finding through the existing disposition flow
    (cases/manager.py:disposition_adverse_media_finding) -- see
    cases/manager.py's pipeline wrapper, which writes every pipeline finding
    into the SAME adverse_media_findings table the legacy path uses, with
    the same default status='open', specifically so that flow needs no
    changes.

Logging discipline (data protection): this module's log lines never include
article text or the customer's name -- only ids, urls' domains, and counts.
Every log line is additionally passed through `amlkit.pii.redact()` before
being emitted, on top of (not instead of) the redaction StructuredFormatter
already applies to every log line in this app (see logging_config.py) --
belt and suspenders, because a pipeline handling third-party news text about
a named individual is exactly the kind of code a future change could
accidentally start logging raw text from.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .. import pii
from ..ai import gemini
from ..db import audit, utcnow
from ..names.arabic import canonical_tokens
from .adverse_media import (
    DEFAULT_WINDOW_MONTHS,
    SEVERITY_FINANCIAL_CRIME,
    SEVERITY_NONE,
    SEVERITY_REGULATORY,
    SEVERITY_REPUTATIONAL,
    Article,
    GDELTClient,
    MediaClient,
    MediaUnavailable,
    build_query,
    parse_articles,
    worst_severity,
)
from .adverse_media import _name_evidence as _keyword_name_evidence
from .adverse_media import (
    classify as keyword_classify,
)
from .gdelt_bq import GdeltBqScreener
from .knowledge_graph import KnowledgeGraphScreener
from .nl_entities import NaturalLanguageScreener
from .vertex_search import VertexAiSearchScreener

log = logging.getLogger("amlkit.screening.media_pipeline")

# Hard cap on candidate articles carried past acquisition, across all three
# sources combined -- keeps stage 2/3 API spend bounded regardless of how
# common a name is.
MAX_ARTICLES = 50

# How many articles go into one Gemini triage call. Batched (rather than one
# call per article) to keep call count, and therefore latency and cost,
# bounded for a customer with a large candidate set.
TRIAGE_BATCH_SIZE = 8

# Cloud NL salience is a 0..1 share of the document "about" that entity.
# 0.02 is a low bar deliberately: this filter's job is to drop entities that
# are clearly a different person / an incidental mention, not to be the
# precision mechanism -- that is triage's job (or classify()'s, when triage
# is off). Configurable because a firm screening very common names may want
# it stricter.
DEFAULT_NL_SALIENCE_THRESHOLD = 0.02

# Bridges Gemini's triage severity vocabulary (low/medium/high) onto the
# three-tier vocabulary screening/adverse_media.py and risk/ruleset.yaml
# already use, so a pipeline-sourced finding feeds the risk model exactly
# like a classify()-sourced one -- same reasoning as adverse_media.py's own
# SEVERITY_ORDER comment: one vocabulary, no translation table to drift.
TRIAGE_TO_RISK_SEVERITY: dict[str, str] = {
    "high": SEVERITY_FINANCIAL_CRIME,
    "medium": SEVERITY_REGULATORY,
    "low": SEVERITY_REPUTATIONAL,
}


def _log(level: int, message: str) -> None:
    """Log a line that has already been through pii.redact().

    See the module docstring's "Logging discipline" note: every call site in
    this module passes only ids/urls/counts, and this wrapper redacts the
    formatted message anyway, defense in depth against a future call site
    that forgets and interpolates something it should not.
    """
    log.log(level, pii.redact(message))


class TenantMismatchError(ValueError):
    """Raised when `customer_id` does not belong to `org_id`."""


@dataclass
class PipelineClients:
    """Dependency injection bundle for `run_pipeline`.

    Every field defaults to the real Google-calling client, constructed
    lazily (only when actually used, and only import-time-lazy inside each
    client class -- see screening/gdelt_bq.py's `_make_bq_client` for the
    established pattern). Tests pass fakes for whichever stages they are
    exercising; unset fields fall back to the real thing, so a fake set only
    needs to cover the sources a test cares about as long as the others stay
    disabled via env vars (AMLKIT_VAIS_ENABLED / AMLKIT_NL_ENABLED /
    AMLKIT_MEDIA_TRIAGE_ENABLED all default to 0).
    """

    gdelt_client: MediaClient | None = None
    gdelt_bq: GdeltBqScreener | None = None
    vertex_search: VertexAiSearchScreener | None = None
    knowledge_graph: KnowledgeGraphScreener | None = None
    nl: NaturalLanguageScreener | None = None
    triage_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None


@dataclass
class PipelineArticleResult:
    url: str
    title: str
    domain: str
    language: str
    source: str  # gdelt_doc | gdelt_bq | vertex_search
    published_at: str | None
    salience: float | None
    sentiment_score: float | None
    sentiment_magnitude: float | None
    kg_match: bool
    name_evidence: str  # title | body
    relevant: bool
    categories: list[str]
    severity: str  # amlkit's financial_crime_alleged | regulatory_action | reputational_only | none
    rationale: str
    english_headline: str
    model_id: str | None
    prompt_version: str | None


@dataclass
class PipelineRunResult:
    run_id: int
    customer_id: int
    query_name: str
    query_arabic: str | None
    status: str  # ok | partial | unavailable
    started_at: str
    finished_at: str
    sources_queried: dict[str, int] = field(default_factory=dict)
    # Total distinct (deduped) candidates acquisition returned, BEFORE entity
    # resolution narrows them down -- independent of `len(articles)` below.
    # articles_considered >= len(articles) >= len(relevant_articles).
    articles_considered: int = 0
    # One entry per candidate that passed stage 2 (entity resolution), scored
    # by stage 3 -- relevant AND not-relevant, so a triage run that found
    # "nothing adverse" still has a full evidence trail. See the module
    # docstring and db.py's media_pipeline_articles comment.
    articles: list[PipelineArticleResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def relevant_articles(self) -> list[PipelineArticleResult]:
        return [a for a in self.articles if a.relevant]

    @property
    def severity(self) -> str:
        return worst_severity(a.severity for a in self.relevant_articles)


@dataclass
class _Candidate:
    article: Article
    source: str
    snippet: str = ""


def _normalize_url(url: str) -> str:
    """Scheme/host/path only, lower-cased, no query/fragment/trailing slash/www.

    The three acquisition sources can return the same article with different
    tracking query strings or a "www." prefix on one and not another; a
    de-dupe keyed on the raw string would double-count it.
    """
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url.lower()
    netloc = parts.netloc.lower()
    netloc = netloc.removeprefix("www.")
    path = parts.path.rstrip("/")
    return urlunsplit(("https", netloc, path, "", ""))


def _chunks(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


# ------------------------------------------------------------------ stage 1
def _acquire(
    name: str,
    name_arabic: str | None,
    *,
    clients: PipelineClients,
    window_months: int,
) -> tuple[list[_Candidate], dict[str, int], list[str]]:
    seen: set[str] = set()
    candidates: list[_Candidate] = []
    sources_queried = {"gdelt_doc": 0, "gdelt_bq": 0, "vertex_search": 0}
    errors: list[str] = []

    def _add(article: Article, source: str, snippet: str = "") -> bool:
        key = _normalize_url(article.url)
        if not key or key in seen or len(candidates) >= MAX_ARTICLES:
            return False
        seen.add(key)
        candidates.append(_Candidate(article=article, source=source, snippet=snippet))
        sources_queried[source] += 1
        return True

    # --- GDELT DOC 2.0 (global news) ---
    gdelt_client = clients.gdelt_client or GDELTClient()
    queries = [name]
    if name_arabic and name_arabic.strip() and name_arabic.strip() != name:
        queries.append(name_arabic.strip())
    for q in queries:
        if len(candidates) >= MAX_ARTICLES:
            break
        try:
            payload = gdelt_client.fetch(
                build_query(q), window_months=window_months, max_records=MAX_ARTICLES
            )
        except MediaUnavailable as exc:
            errors.append(f"gdelt_doc: {exc}")
            continue
        for art in parse_articles(payload):
            _add(art, "gdelt_doc")
            if len(candidates) >= MAX_ARTICLES:
                break

    # --- BigQuery GDELT GKG ---
    if len(candidates) < MAX_ARTICLES:
        bq = clients.gdelt_bq or GdeltBqScreener()
        bq_result = bq.screen(name, window_days=max(1, window_months) * 30)
        if bq_result.status == "unavailable":
            errors.append("gdelt_bq: unavailable")
        elif bq_result.status == "ok":
            # GdeltBqResult.sample_headlines holds DocumentIdentifier values
            # (article URLs), not headline text -- GKG's row shape has no
            # separate headline field. See screening/gdelt_bq.py.
            for url in bq_result.sample_headlines:
                if len(candidates) >= MAX_ARTICLES:
                    break
                domain = ""
                try:
                    domain = urlsplit(url).netloc
                except ValueError:
                    pass
                _add(Article(url=url, title="", domain=domain), "gdelt_bq")

    # --- Vertex AI Search (targeted regional/UAE press) ---
    if len(candidates) < MAX_ARTICLES and os.environ.get("AMLKIT_VAIS_ENABLED", "0") == "1":
        vais = clients.vertex_search or VertexAiSearchScreener()
        vais_result = vais.search(name, max_results=MAX_ARTICLES - len(candidates))
        if vais_result.status == "unavailable":
            errors.append("vertex_search: unavailable")
        elif vais_result.status == "ok":
            for a in vais_result.articles:
                if len(candidates) >= MAX_ARTICLES:
                    break
                domain = ""
                try:
                    domain = urlsplit(a.url).netloc
                except ValueError:
                    pass
                _add(
                    Article(url=a.url, title=a.title, domain=domain),
                    "vertex_search",
                    snippet=a.snippet,
                )

    return candidates[:MAX_ARTICLES], sources_queried, errors


# ------------------------------------------------------------------ stage 2
def _resolve_entities(
    name: str,
    candidates: list[_Candidate],
    *,
    clients: PipelineClients,
) -> tuple[list[_Candidate], dict[str, dict[str, Any]]]:
    """Filter candidates to those with evidence they are about `name`.

    Returns (kept_candidates, meta_by_url) where meta_by_url carries
    salience/sentiment/kg_match/name_evidence plus, when the NL path is off,
    the keyword-classify() fallback's severity/terms so stage 3 can use them
    without re-deriving.
    """
    kg = clients.knowledge_graph or KnowledgeGraphScreener()
    kg_result = kg.screen(name)
    kg_mids = (
        {e.kg_id for e in kg_result.entities if e.kg_id}
        if kg_result.status == "ok"
        else set()
    )

    nl_enabled = os.environ.get("AMLKIT_NL_ENABLED", "0") == "1"
    kept: list[_Candidate] = []
    meta: dict[str, dict[str, Any]] = {}

    if not nl_enabled:
        for cand in candidates:
            evidence = _keyword_name_evidence(name, cand.article.title)
            severity, terms = keyword_classify(cand.article.title)
            if severity == SEVERITY_NONE:
                # No lexicon hit on the headline -- exactly the case
                # search()/adverse_media.py already declines to keep (no
                # evidence an operator can be shown). Consistent behaviour
                # with AMLKIT_NL_ENABLED=0 leaving legacy behaviour intact.
                continue
            kept.append(cand)
            meta[cand.article.url] = {
                "salience": None,
                "sentiment_score": None,
                "sentiment_magnitude": None,
                "kg_match": False,
                "name_evidence": evidence,
                "fallback_severity": severity,
                "fallback_terms": terms,
            }
        return kept, meta

    nl = clients.nl or NaturalLanguageScreener()
    threshold = float(
        os.environ.get("AMLKIT_NL_SALIENCE_THRESHOLD", str(DEFAULT_NL_SALIENCE_THRESHOLD))
    )
    name_tokens = set(canonical_tokens(name))

    for cand in candidates:
        # Keyword classify() runs regardless of the NL path being on: it costs
        # no API call, and stage 3's non-Gemini fallback needs a severity
        # source even for a candidate that NL (not a keyword) is what kept.
        evidence = _keyword_name_evidence(name, cand.article.title)
        fallback_severity, fallback_terms = keyword_classify(cand.article.title)

        text = " ".join(t for t in (cand.article.title, cand.snippet) if t).strip()
        nl_result = nl.analyze(text)
        if nl_result.status != "ok" or not nl_result.entities:
            continue

        best = None
        for ent in nl_result.entities:
            ent_tokens = set(canonical_tokens(ent.name))
            if not ent_tokens or not name_tokens:
                continue
            # Same "every token must be covered" precision rule as
            # adverse_media._name_evidence -- a partial token match (one
            # given name in common) is not evidence of the same person.
            is_match = name_tokens.issubset(ent_tokens) or ent_tokens.issubset(name_tokens)
            if is_match and (best is None or ent.salience > best.salience):
                best = ent
        if best is None or best.salience < threshold:
            continue

        kept.append(cand)
        meta[cand.article.url] = {
            "salience": best.salience,
            "sentiment_score": best.sentiment_score,
            "sentiment_magnitude": best.sentiment_magnitude,
            "kg_match": bool(best.mid and best.mid in kg_mids),
            "name_evidence": evidence,
            "fallback_severity": fallback_severity,
            "fallback_terms": fallback_terms,
        }

    return kept, meta


# ------------------------------------------------------------------ stage 3
#
# Every candidate stage 2 kept gets exactly one PipelineArticleResult here --
# relevant or not. Nothing is silently dropped: a candidate stage 2 judged
# "about this customer" that stage 3 then judges "not adverse" is still part
# of the evidence trail (it is what "considered, found nothing" MEANS), and a
# candidate a Gemini call could not score (provider down, malformed JSON) is
# recorded as un-scoreable with a rationale saying so, never conflated with
# "found not relevant".
def _fallback_result(cand: _Candidate, m: dict[str, Any]) -> PipelineArticleResult:
    fallback_severity = m.get("fallback_severity") or SEVERITY_NONE
    terms = m.get("fallback_terms") or []
    relevant = fallback_severity != SEVERITY_NONE
    return PipelineArticleResult(
        url=cand.article.url,
        title=cand.article.title,
        domain=cand.article.domain,
        language=cand.article.language,
        source=cand.source,
        published_at=cand.article.published_at,
        salience=m.get("salience"),
        sentiment_score=m.get("sentiment_score"),
        sentiment_magnitude=m.get("sentiment_magnitude"),
        kg_match=bool(m.get("kg_match")),
        name_evidence=m.get("name_evidence", "body"),
        relevant=relevant,
        categories=[],
        severity=fallback_severity if relevant else SEVERITY_NONE,
        rationale=("keyword match: " + ", ".join(terms)) if terms else "",
        english_headline=cand.article.title,
        model_id=None,
        prompt_version=None,
    )


def _unscoreable_result(cand: _Candidate, m: dict[str, Any], reason: str) -> PipelineArticleResult:
    return PipelineArticleResult(
        url=cand.article.url,
        title=cand.article.title,
        domain=cand.article.domain,
        language=cand.article.language,
        source=cand.source,
        published_at=cand.article.published_at,
        salience=m.get("salience"),
        sentiment_score=m.get("sentiment_score"),
        sentiment_magnitude=m.get("sentiment_magnitude"),
        kg_match=bool(m.get("kg_match")),
        name_evidence=m.get("name_evidence", "body"),
        relevant=False,
        categories=[],
        severity=SEVERITY_NONE,
        rationale=reason,
        english_headline=cand.article.title,
        model_id=gemini.GEMINI_MODEL,
        prompt_version=f"{gemini.TRIAGE_PROMPT_VERSION}:{gemini.triage_prompt_hash()}",
    )


def _triage(
    candidates: list[_Candidate],
    meta: dict[str, dict[str, Any]],
    *,
    clients: PipelineClients,
) -> list[PipelineArticleResult]:
    triage_enabled = os.environ.get("AMLKIT_MEDIA_TRIAGE_ENABLED", "0") == "1"

    if not triage_enabled:
        return [_fallback_result(cand, meta.get(cand.article.url, {})) for cand in candidates]

    triage_fn = clients.triage_fn or gemini.triage_adverse_media
    results: list[PipelineArticleResult] = []
    for batch in _chunks(candidates, TRIAGE_BATCH_SIZE):
        payload = [
            {"id": str(i), "title": c.article.title, "snippet": c.snippet}
            for i, c in enumerate(batch)
        ]
        try:
            triaged = triage_fn(payload)
        except gemini.GeminiUnavailable as exc:
            _log(logging.WARNING, f"gemini triage unavailable for a batch of {len(batch)}: {exc}")
            for cand in batch:
                results.append(_unscoreable_result(
                    cand, meta.get(cand.article.url, {}), f"triage unavailable: {exc}"
                ))
            continue

        by_id = {t["id"]: t for t in triaged}
        for i, cand in enumerate(batch):
            t = by_id.get(str(i))
            m = meta.get(cand.article.url, {})
            if t is None:
                results.append(_unscoreable_result(
                    cand, m, "triage output failed schema validation"
                ))
                continue
            relevant = bool(t.get("relevant"))
            results.append(
                PipelineArticleResult(
                    url=cand.article.url,
                    title=cand.article.title,
                    domain=cand.article.domain,
                    language=t.get("language") or cand.article.language,
                    source=cand.source,
                    published_at=cand.article.published_at,
                    salience=m.get("salience"),
                    sentiment_score=m.get("sentiment_score"),
                    sentiment_magnitude=m.get("sentiment_magnitude"),
                    kg_match=bool(m.get("kg_match")),
                    name_evidence=m.get("name_evidence", "body"),
                    relevant=relevant,
                    categories=list(t.get("categories") or []),
                    severity=(
                        TRIAGE_TO_RISK_SEVERITY.get(t.get("severity", ""), SEVERITY_REPUTATIONAL)
                        if relevant else SEVERITY_NONE
                    ),
                    rationale=t.get("rationale") or "",
                    english_headline=t.get("english_headline") or cand.article.title,
                    model_id=gemini.GEMINI_MODEL,
                    prompt_version=f"{gemini.TRIAGE_PROMPT_VERSION}:{gemini.triage_prompt_hash()}",
                )
            )
    return results


# ------------------------------------------------------------------ stage 4
def _persist_run(
    conn: sqlite3.Connection,
    *,
    org_id: int,
    customer_id: int,
    trigger: str,
    query_name: str,
    query_arabic: str | None,
    started_at: str,
) -> int:
    with conn:
        cur = conn.execute(
            """INSERT INTO media_pipeline_runs
               (org_id, customer_id, trigger, status, query_name, query_arabic,
                sources_queried, articles_considered, articles_relevant, errors,
                started_at, finished_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                org_id, customer_id, trigger, "pending", query_name, query_arabic,
                json.dumps({}), 0, 0, None, started_at, None, started_at,
            ),
        )
        run_id = cur.lastrowid
        audit(
            conn, "system", "media_pipeline.run.start", "customer", customer_id,
            {"run_id": run_id, "trigger": trigger},
            org_id=org_id,
        )
    return run_id


def _finish_run(
    conn: sqlite3.Connection,
    *,
    org_id: int,
    customer_id: int,
    run_id: int,
    actor: str,
    status: str,
    sources_queried: dict[str, int],
    articles_considered: int,
    articles: list[PipelineArticleResult],
    errors: list[str],
    finished_at: str,
) -> None:
    relevant = [a for a in articles if a.relevant]
    with conn:
        conn.execute(
            """UPDATE media_pipeline_runs
               SET status=?, sources_queried=?, articles_considered=?,
                   articles_relevant=?, errors=?, finished_at=?
               WHERE id=? AND org_id=?""",
            (
                status, json.dumps(sources_queried), articles_considered, len(relevant),
                json.dumps(errors) if errors else None, finished_at, run_id, org_id,
            ),
        )
        for a in articles:
            cur = conn.execute(
                """INSERT INTO media_pipeline_articles
                   (org_id, run_id, customer_id, url, source, title, domain, language,
                    published_at, salience, sentiment_score, sentiment_magnitude,
                    kg_match, relevant, categories, severity, rationale,
                    english_headline, model_id, prompt_version, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    org_id, run_id, customer_id, a.url, a.source, a.title, a.domain,
                    a.language, a.published_at, a.salience, a.sentiment_score,
                    a.sentiment_magnitude, int(a.kg_match), int(a.relevant),
                    json.dumps(a.categories, ensure_ascii=False), a.severity,
                    a.rationale, a.english_headline, a.model_id, a.prompt_version,
                    finished_at,
                ),
            )
            if a.relevant:
                # A finding is "surfaced" to a human the moment it is
                # written here -- see the module docstring: this NEVER
                # dispositions it, only records that the pipeline is asking
                # an operator to look at it.
                audit(
                    conn, actor, "media_pipeline.finding.surfaced",
                    "media_pipeline_article", cur.lastrowid,
                    {
                        "run_id": run_id,
                        "source": a.source,
                        "severity": a.severity,
                        "categories": a.categories,
                        "kg_match": a.kg_match,
                    },
                    org_id=org_id,
                )
        audit(
            conn, actor, "media_pipeline.run.finish", "customer", customer_id,
            {
                "run_id": run_id,
                "status": status,
                "sources_queried": sources_queried,
                "articles_considered": len(articles),
                "articles_relevant": len(relevant),
                "errors": errors,
            },
            org_id=org_id,
        )


def _customer_name(
    conn: sqlite3.Connection, customer_id: int, org_id: int
) -> tuple[str, str | None]:
    row = conn.execute(
        "SELECT full_name, name_arabic FROM customers WHERE id=? AND org_id=?",
        (customer_id, org_id),
    ).fetchone()
    if row is None:
        raise TenantMismatchError(
            f"customer {customer_id} not found for this organisation"
        )
    return row["full_name"], row["name_arabic"]


def run_pipeline(
    conn: sqlite3.Connection,
    org_id: int,
    customer_id: int,
    actor: str = "system",
    *,
    clients: PipelineClients | None = None,
    trigger: str = "adhoc",
    window_months: int = DEFAULT_WINDOW_MONTHS,
) -> PipelineRunResult:
    """Run the 4-stage adverse-media pipeline for one customer.

    Tenant isolation: `customer_id` is resolved by `SELECT ... WHERE id=? AND
    org_id=?` -- a customer belonging to a different org raises
    TenantMismatchError (a ValueError) before any Google API is touched, so a
    cross-org call costs nothing and writes nothing.

    Every write is scoped to `org_id` (media_pipeline_runs, media_pipeline_articles,
    and every audit() call). Findings are never auto-dispositioned here -- see
    the module docstring.
    """
    clients = clients or PipelineClients()
    started_at = utcnow()

    name, name_arabic = _customer_name(conn, customer_id, org_id)
    run_id = _persist_run(
        conn, org_id=org_id, customer_id=customer_id, trigger=trigger,
        query_name=name, query_arabic=name_arabic, started_at=started_at,
    )
    _log(logging.INFO, f"media_pipeline run {run_id} started for customer {customer_id}")

    candidates, sources_queried, acquire_errors = _acquire(
        name, name_arabic, clients=clients, window_months=window_months
    )
    kept, meta = _resolve_entities(name, candidates, clients=clients)
    articles = _triage(kept, meta, clients=clients)
    articles_considered = len(candidates)

    errors = list(acquire_errors)
    total_queried = sum(sources_queried.values())
    if total_queried == 0 and errors:
        status = "unavailable"
    elif errors:
        status = "partial"
    else:
        status = "ok"

    finished_at = utcnow()
    _finish_run(
        conn, org_id=org_id, customer_id=customer_id, run_id=run_id, actor=actor,
        status=status, sources_queried=sources_queried,
        articles_considered=articles_considered, articles=articles,
        errors=errors, finished_at=finished_at,
    )
    _log(
        logging.INFO,
        f"media_pipeline run {run_id} finished status={status} "
        f"considered={articles_considered} scored={len(articles)} "
        f"relevant={sum(1 for a in articles if a.relevant)}",
    )

    return PipelineRunResult(
        run_id=run_id,
        customer_id=customer_id,
        query_name=name,
        query_arabic=name_arabic,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        sources_queried=sources_queried,
        articles_considered=articles_considered,
        articles=articles,
        errors=errors,
    )
