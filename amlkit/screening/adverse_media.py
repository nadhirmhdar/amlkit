"""Adverse media screening against GDELT DOC 2.0.

Cabinet Resolution No. 134 of 2025 expects a risk-based approach that looks
beyond list matching: negative news is one of the standard EDD inputs, and
`risk/ruleset.yaml` has carried an `adverse_media` factor since the risk model
was written. Until now nothing fed it -- every assessment scored that factor
`none` because no code ever supplied a value. This module is what supplies it.

Why GDELT rather than a commercial media vendor
-----------------------------------------------
Curated adverse-media corpora (World-Check, Dow Jones, LexisNexis) are the
single largest line item in a commercial screening subscription, and they are
priced for banks -- see `research/pricing-teardown.md`. GDELT indexes global
news in 65+ languages, is queryable without an API key, and its terms are
unusually clear: "all datasets released by the GDELT Project are available for
unlimited and unrestricted use for any academic, commercial, or governmental
use of any kind without fee", conditional only on citing the project. That
clears the same commercial bar every ingest adapter in this codebase had to
clear (see `ingest/base.py`), which is why it is here and OpenSanctions' data
is not.

What this is NOT
----------------
This is a **screening aid, not a curated adverse-media database**. GDELT is an
index of news coverage, not an assessed risk file: nobody has decided that an
article is about *your* customer, or that its allegation is credible. A
commercial vendor sells that human assessment, and this does not replace it.
Every finding here is an unreviewed lead that an operator must open and judge,
which is why findings are dispositioned rather than scored, and why nothing
here touches a risk rating until a human marks it relevant.

Three structural design choices, stated because each is a deliberate trade:

1. **Query-time, not ingested.** Every other source in this codebase is bulk
   loaded by `ingest/loader.py` and screened locally. News cannot work that
   way -- there is no list to snapshot, and the relevant corpus is defined by
   the name being searched. So adverse media lives in `screening/` beside
   `kyt.py` and `pf.py`, not in `ingest/`.

2. **Failure is soft, not loud.** `ingest/base.py` makes adapter failures
   deliberately loud, because a silently-lapsed *sanctions* feed shows green
   while a legal obligation goes unmet. Adverse media is the opposite case:
   it is a risk-based input, not a mandatory list, and a third-party news API
   being down must never block onboarding a customer. So a failed search
   returns `status="unavailable"` and is recorded as such -- the screening row
   still exists and still says, on the record, that the check was attempted
   and did not complete. Degraded, and visibly so, rather than either silent
   or blocking.

3. **Not run automatically on every refresh.** `rescreen_all` re-screens every
   customer against the sanctions lists after each dataset refresh. Adverse
   media deliberately does not join that path: GDELT rate-limits to roughly
   one request every 5 seconds, so a 400-customer book would take over an hour
   of wall-clock throttling and hammer a free public service on a 20-hour
   cycle. It is an explicit per-customer action instead, and periodic re-runs
   belong to the review cycle the risk rating already schedules.

Attribution
-----------
GDELT's terms require a citation and a link wherever its data is used or
redistributed. `ATTRIBUTION` below is that citation; it is rendered in the UI
and written into the evidence pack, not left to a developer to remember.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Protocol
from urllib.parse import urlencode

import httpx

from ..names.arabic import canonical_tokens

ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"

ATTRIBUTION = (
    "Adverse media coverage indexed by The GDELT Project "
    "(https://www.gdeltproject.org/)."
)

# GDELT asks for no more than one request every 5 seconds and enforces it with
# a 429 carrying a plain-text body. The limit is per source IP, so every caller
# in one process shares one budget -- hence a module-level gate rather than a
# per-client one. 5.5s, not 5.0: the limit is enforced on GDELT's clock, not
# ours, and a request that leaves exactly on the boundary arrives just inside
# the previous window often enough to matter.
MIN_REQUEST_INTERVAL = 5.5
_rate_gate = threading.Lock()
_last_request_at = 0.0

# GDELT's own documented ceiling for artlist. Asking for more is not an error,
# it is silently capped, so the cap is stated here rather than discovered.
MAX_RECORDS = 250

# How far back to look. GDELT's DOC API searches a rolling ~3-month window by
# default and can reach back to 1 January 2017 with an explicit date range.
# 24 months is the default here because adverse media relevant to a CDD file
# is not confined to the last quarter -- a 2023 fraud conviction is exactly
# what this check exists to surface -- while going all the way to 2017 on
# every search returns a decade of noise for common names.
DEFAULT_WINDOW_MONTHS = 24
GDELT_EARLIEST = datetime(2017, 1, 1, tzinfo=timezone.utc)

# Severity vocabulary. These four strings are NOT invented here: they are the
# exact keys of `factors.adverse_media.points_by_severity` in
# risk/ruleset.yaml. Keeping them identical is what lets a dispositioned
# finding feed the risk model without a translation table that could drift.
SEVERITY_FINANCIAL_CRIME = "financial_crime_alleged"
SEVERITY_REGULATORY = "regulatory_action"
SEVERITY_REPUTATIONAL = "reputational_only"
SEVERITY_NONE = "none"

# Ordered worst-first. Used to pick one severity for a set of findings and to
# compare two severities without scattering comparison logic around.
SEVERITY_ORDER: tuple[str, ...] = (
    SEVERITY_FINANCIAL_CRIME,
    SEVERITY_REGULATORY,
    SEVERITY_REPUTATIONAL,
    SEVERITY_NONE,
)

# --------------------------------------------------------------- risk lexicon
#
# Three tiers, mapped onto the ruleset's three non-zero severities. The split
# is by *what happened*, not by how bad it sounds: an administrative fine and a
# money-laundering indictment are both adverse, but they are different facts
# about a customer and the risk model already prices them differently (25 vs
# 35 points).
#
# Arabic terms are first-class here rather than an afterthought. The whole
# premise of this codebase is that UAE screening is an Arabic problem (see
# names/arabic.py), and that applies to the coverage as much as to the names:
# a Gulf fraud case is frequently reported in Arabic days before any English
# outlet picks it up, if one ever does. GDELT indexes Arabic-language news, so
# searching only English would systematically miss the region's own reporting
# about its own residents.

FINANCIAL_CRIME_TERMS: tuple[str, ...] = (
    "money laundering", "laundering", "terrorist financing", "terrorism financing",
    "financing of terrorism", "fraud", "fraudulent", "bribery", "bribe",
    "corruption", "embezzlement", "embezzled", "kickback", "racketeering",
    "extortion", "smuggling", "human trafficking", "drug trafficking",
    "narcotics", "tax evasion", "ponzi", "pyramid scheme", "forgery", "forged",
    "counterfeiting", "insider trading", "market manipulation",
    "sanctions evasion", "proliferation financing", "organised crime",
    "organized crime", "cartel", "indicted", "indictment", "convicted",
    "conviction", "criminal charges", "charged with", "arrested", "arrest warrant",
    # Arabic
    "غسل الأموال", "غسيل الأموال", "تمويل الإرهاب", "احتيال", "نصب واحتيال",
    "رشوة", "رشاوى", "فساد", "اختلاس", "تهريب", "تزوير", "تهرب ضريبي",
    "الاتجار بالبشر", "مخدرات", "إدانة", "أدين", "توقيف", "اعتقال",
)

REGULATORY_TERMS: tuple[str, ...] = (
    "fined", "fine of", "penalty", "penalised", "penalized", "sanctioned by",
    "enforcement action", "regulatory action", "censure", "censured",
    "reprimand", "cease and desist", "consent order", "licence revoked",
    "license revoked", "licence suspended", "license suspended", "struck off",
    "debarred", "disqualified", "blacklisted", "banned from", "barred from",
    "investigation", "investigated", "probe", "raided", "regulator",
    "lawsuit", "sued", "settlement with", "court order", "asset freeze",
    "frozen assets", "wound up", "liquidation order",
    # Arabic
    "غرامة", "عقوبة", "تحقيق", "مخالفة", "سحب الرخصة", "إيقاف الترخيص",
    "حظر", "قائمة سوداء", "دعوى قضائية", "أمر قضائي", "تجميد الأصول",
)

REPUTATIONAL_TERMS: tuple[str, ...] = (
    "scandal", "controversy", "controversial", "allegation", "alleged",
    "accused", "accusation", "misconduct", "whistleblower", "leaked documents",
    "offshore leaks", "panama papers", "pandora papers", "paradise papers",
    "resigned amid", "stepped down amid", "ousted", "conflict of interest",
    "questioned over", "under scrutiny", "denies wrongdoing",
    # Arabic
    "فضيحة", "جدل", "اتهام", "اتهامات", "مزاعم", "سوء سلوك", "تضارب المصالح",
    "استقال", "أقيل", "وثائق مسربة",
)

_TIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (SEVERITY_FINANCIAL_CRIME, FINANCIAL_CRIME_TERMS),
    (SEVERITY_REGULATORY, REGULATORY_TERMS),
    (SEVERITY_REPUTATIONAL, REPUTATIONAL_TERMS),
)

# Terms sent to GDELT to narrow the search server-side. Deliberately a subset
# of the lexicon above: GDELT rejects over-long queries, and the point of the
# server-side filter is recall of *adverse* coverage, not exhaustive
# classification -- that happens locally in `classify()` against the full
# lexicon. A name with a thousand neutral mentions and one fraud story should
# return the fraud story, which an unfiltered name query would bury past the
# 250-record ceiling.
_QUERY_TERMS: tuple[str, ...] = (
    "fraud", "bribery", "corruption", "laundering", "embezzlement",
    "smuggling", "trafficking", "terrorism", "sanctions", "investigation",
    "arrested", "convicted", "indicted", "fined", "penalty", "lawsuit",
    "scandal", "allegation", "misconduct",
    "احتيال", "رشوة", "فساد", "غسل الأموال", "اختلاس", "تهريب",
    "تحقيق", "اعتقال", "إدانة", "غرامة", "فضيحة", "اتهام",
)


@dataclass(slots=True)
class Article:
    """One article as GDELT returned it. Metadata only, deliberately.

    GDELT's own data is free to use commercially; the articles it indexes are
    not -- each one is its publisher's copyright. So this stores the metadata
    GDELT publishes (URL, title, outlet, date, language) and links out. It
    never fetches or stores article text, which would be republishing someone
    else's content under this tool's name.
    """

    url: str
    title: str
    domain: str = ""
    language: str = ""
    source_country: str = ""
    published_at: str | None = None


@dataclass(slots=True)
class Finding:
    """An article that mentions the screened name and carries a risk term."""

    article: Article
    severity: str
    matched_terms: list[str] = field(default_factory=list)
    # 'title' when the searched name is visible in the headline, 'body' when
    # GDELT matched it somewhere in the article we cannot see. See
    # `_name_evidence` for why this distinction is recorded rather than used
    # to silently drop the weaker half.
    name_evidence: str = "body"


@dataclass(slots=True)
class AdverseMediaResult:
    query: str
    query_arabic: str | None = None
    findings: list[Finding] = field(default_factory=list)
    articles_considered: int = 0
    window_months: int = DEFAULT_WINDOW_MONTHS
    # 'ok' or 'unavailable'. An empty `findings` list means opposite things
    # under the two, and conflating them is how a compliance file ends up
    # recording "nothing adverse found" for a check that never ran.
    status: str = "ok"
    error: str | None = None
    provider: str = "gdelt"

    @property
    def severity(self) -> str:
        """Worst severity across findings; `none` when there are none."""
        return worst_severity(f.severity for f in self.findings)

    @property
    def clear(self) -> bool:
        return self.status == "ok" and not self.findings

    def summary(self) -> str:
        if self.status != "ok":
            return f"UNAVAILABLE  adverse media for '{self.query}' - {self.error}"
        if self.clear:
            return (
                f"CLEAR  no adverse coverage for '{self.query}' in the last "
                f"{self.window_months} months ({self.articles_considered} articles screened)"
            )
        return (
            f"FINDINGS  {len(self.findings)} adverse article(s) for '{self.query}', "
            f"highest severity {self.severity} ({self.articles_considered} screened)"
        )


def worst_severity(severities: Iterable[str]) -> str:
    """Most serious severity in `severities`, or `none` if empty/unrecognised.

    Materialises the argument first. Callers pass generators (a database
    cursor, a comprehension over findings), and scanning one once per tier
    would exhaust it on the first tier -- silently scoring every
    regulatory-action and reputational finding as `none` while
    financial-crime ones, checked first, worked fine.
    """
    present = set(severities)
    for level in SEVERITY_ORDER:
        if level == SEVERITY_NONE:
            break
        if level in present:
            return level
    return SEVERITY_NONE


class MediaClient(Protocol):
    """The seam that keeps tests off the network.

    Same purpose as `SourceAdapter` in ingest: one narrow interface, so the
    thing that talks to the internet can be swapped for a stub without the
    classification logic knowing. Tests exercise `search()` end to end against
    a canned payload; nothing in the suite hits GDELT.
    """

    def fetch(self, query: str, *, window_months: int, max_records: int) -> dict[str, Any]:
        """Return GDELT's decoded artlist JSON, or raise `MediaUnavailable`."""


class MediaUnavailable(RuntimeError):
    """The media provider could not be reached or returned something unusable.

    Caught by `search()` and turned into `status="unavailable"` rather than
    propagated: see design note 2 in the module docstring. Raised, not
    returned, so that a caller using the client directly cannot mistake a
    failed fetch for an empty result set.
    """


class GDELTClient:
    """Rate-limited GDELT DOC 2.0 client."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def fetch(
        self, query: str, *, window_months: int, max_records: int
    ) -> dict[str, Any]:
        params = {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": str(min(max_records, MAX_RECORDS)),
            "sort": "datedesc",
            **_date_range(window_months),
        }
        url = f"{ENDPOINT}?{urlencode(params)}"
        _throttle()
        try:
            r = httpx.get(
                url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
        except httpx.HTTPError as exc:
            raise MediaUnavailable(f"GDELT request failed: {exc}") from exc

        if r.status_code == 429:
            raise MediaUnavailable(
                "GDELT rate limit reached (one request per 5s per source IP); "
                "try again shortly"
            )
        if r.status_code >= 400:
            raise MediaUnavailable(f"GDELT returned HTTP {r.status_code}")

        # GDELT answers a malformed query with HTTP 200 and an HTML error page
        # rather than an error status, so status_code alone does not tell us
        # the request succeeded. Without this check the JSON decode below
        # fails on a page of markup and reports "invalid JSON", which sends
        # whoever debugs it looking in entirely the wrong place.
        body = r.text.strip()
        if not body:
            raise MediaUnavailable("GDELT returned an empty body")
        if not body.startswith("{"):
            raise MediaUnavailable(f"GDELT rejected the query: {body[:200]}")

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MediaUnavailable(f"GDELT returned invalid JSON: {exc}") from exc


def _throttle() -> None:
    """Block until at least MIN_REQUEST_INTERVAL has passed since the last call."""
    global _last_request_at
    with _rate_gate:
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def _date_range(window_months: int) -> dict[str, str]:
    """GDELT startdatetime/enddatetime for a rolling window, clamped to 2017.

    An explicit range rather than `timespan=`: `timespan` caps out well short
    of two years, and silently returning three months of coverage while the
    screening record claims twenty-four would be a false statement in a
    compliance file.
    """
    now = datetime.now(timezone.utc)
    months = max(1, int(window_months))
    year = now.year - (months // 12)
    month = now.month - (months % 12)
    if month <= 0:
        month += 12
        year -= 1
    try:
        start = now.replace(year=year, month=month)
    except ValueError:  # e.g. 31 March minus 1 month
        start = now.replace(year=year, month=month, day=1)
    start = max(start, GDELT_EARLIEST)
    fmt = "%Y%m%d%H%M%S"
    return {"startdatetime": start.strftime(fmt), "enddatetime": now.strftime(fmt)}


def build_query(name: str) -> str:
    """GDELT query string: the exact name phrase AND any one risk term.

    Quoting the name makes it a phrase match, so "Ahmed Al Mansoori" does not
    match every article containing "Ahmed". The OR block does the adverse
    filtering server-side -- see the note on `_QUERY_TERMS`.
    """
    terms = " OR ".join(f'"{t}"' if " " in t else t for t in _QUERY_TERMS)
    return f'"{name.strip()}" ({terms})'


def classify(title: str) -> tuple[str, list[str]]:
    """Severity and matched terms for one headline.

    Scans all three tiers rather than stopping at the first hit, so a headline
    reading "fined over money-laundering failings" is classified on the
    laundering allegation rather than on whichever tier happened to be checked
    first. Returns every term that matched, at every tier, because the
    evidence for a classification is part of the record -- same reason
    `alerts.score_detail` stores a per-feature breakdown.
    """
    haystack = (title or "").lower()
    matched: list[str] = []
    severity = SEVERITY_NONE
    for level, terms in _TIERS:
        hits = [t for t in terms if t.lower() in haystack]
        if hits:
            matched.extend(hits)
            if severity == SEVERITY_NONE:
                severity = level
    return severity, matched


def _name_evidence(name: str, title: str) -> str:
    """Whether the searched name is visible in the headline.

    GDELT matched the name somewhere in the article, but artlist only returns
    the headline, so we cannot verify a body match ourselves. A name in the
    headline is strong evidence the piece is *about* that person; a body-only
    match may be a passing mention, a different person with the same name, or
    a quoted source.

    Both are kept. Dropping body-only findings would quietly discard the case
    this check exists for -- "X's company, whose director Y..." is exactly the
    sentence a compliance officer needs to see -- so the weaker evidence is
    labelled rather than hidden, and the operator judges it.

    Uses the Arabic-aware canonical tokens rather than a substring test, so a
    headline spelling the name "Mohd Al-Mansouri" still matches a customer
    recorded as "Mohammed Al Mansoori".
    """
    title_tokens = set(canonical_tokens(title or ""))
    name_tokens = [t for t in canonical_tokens(name) if t]
    if not name_tokens or not title_tokens:
        return "body"
    # Every token of the name must appear. A partial match ("Mohammed" alone
    # out of "Mohammed Al Mansoori") is not evidence the article is about this
    # person -- that is the false-positive mode this whole codebase is built
    # to avoid.
    return "title" if all(t in title_tokens for t in name_tokens) else "body"


def parse_articles(payload: dict[str, Any]) -> list[Article]:
    """Normalise GDELT's artlist JSON into `Article` records.

    Tolerant by design: GDELT has changed field spellings before, and a
    missing `domain` should cost that one column, not the whole screening.
    Only `url` is treated as required, since a finding with no link is not
    evidence of anything.
    """
    out: list[Article] = []
    for row in payload.get("articles") or []:
        if not isinstance(row, dict):
            continue
        url = (row.get("url") or "").strip()
        if not url:
            continue
        out.append(
            Article(
                url=url,
                title=(row.get("title") or "").strip(),
                domain=(row.get("domain") or "").strip(),
                language=(row.get("language") or "").strip(),
                source_country=(row.get("sourcecountry") or "").strip(),
                published_at=_seendate(row.get("seendate")),
            )
        )
    return out


def _seendate(raw: Any) -> str | None:
    """GDELT's `20250903T120000Z` -> ISO-8601, or None if unparseable."""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return (
            datetime.strptime(text, "%Y%m%dT%H%M%SZ")
            .replace(tzinfo=timezone.utc)
            .isoformat(timespec="seconds")
        )
    except ValueError:
        return text or None


def search(
    name: str,
    *,
    name_arabic: str | None = None,
    client: MediaClient | None = None,
    window_months: int = DEFAULT_WINDOW_MONTHS,
    max_records: int = MAX_RECORDS,
) -> AdverseMediaResult:
    """Search adverse coverage for one name, in Latin and Arabic script.

    Never raises for provider failure: a result with `status="unavailable"`
    comes back instead, so a caller onboarding a customer cannot be blocked by
    GDELT being down. Genuine programming errors (a bad argument) still raise.

    When `name_arabic` is given, both spellings are searched and the findings
    merged, deduplicated by URL. That is two requests and therefore ~11
    seconds of throttling, which is the cost of actually covering Arabic-
    language coverage of a Gulf customer rather than only what reached English.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("adverse media search needs a name")

    cl = client or GDELTClient()
    result = AdverseMediaResult(
        query=name,
        query_arabic=(name_arabic or "").strip() or None,
        window_months=window_months,
    )

    queries = [name]
    if result.query_arabic and result.query_arabic != name:
        queries.append(result.query_arabic)

    by_url: dict[str, Finding] = {}
    any_ok = False
    errors: list[str] = []

    for q in queries:
        try:
            payload = cl.fetch(
                build_query(q), window_months=window_months, max_records=max_records
            )
        except MediaUnavailable as exc:
            errors.append(str(exc))
            continue
        any_ok = True
        articles = parse_articles(payload)
        result.articles_considered += len(articles)
        for art in articles:
            severity, matched = classify(art.title)
            if severity == SEVERITY_NONE:
                # GDELT matched a risk term in the body but the headline
                # carries none, so we have nothing we can actually show an
                # operator as the reason this article is adverse. Recording it
                # anyway would fill the queue with rows whose evidence column
                # reads "trust us".
                continue
            finding = Finding(
                article=art,
                severity=severity,
                matched_terms=matched,
                name_evidence=_name_evidence(q, art.title),
            )
            prior = by_url.get(art.url)
            # The same article can come back from both the Latin and Arabic
            # query. Keep the stronger reading of it rather than whichever
            # arrived second.
            if prior is None or _stronger(finding, prior):
                by_url[art.url] = finding

    if not any_ok:
        result.status = "unavailable"
        result.error = "; ".join(errors) or "media provider unavailable"
        return result

    if errors:
        # Partial coverage: one script searched, the other failed. Still 'ok'
        # -- there are real findings -- but the record says what was missed,
        # because "no Arabic coverage found" and "Arabic was never searched"
        # are different facts about this customer's file.
        result.error = "; ".join(errors)

    result.findings = sorted(
        by_url.values(),
        key=lambda f: (
            SEVERITY_ORDER.index(f.severity),
            0 if f.name_evidence == "title" else 1,
            f.article.published_at or "",
        ),
    )
    return result


def _stronger(a: Finding, b: Finding) -> bool:
    """True if `a` is the better-evidenced of two findings for one article."""
    if SEVERITY_ORDER.index(a.severity) != SEVERITY_ORDER.index(b.severity):
        return SEVERITY_ORDER.index(a.severity) < SEVERITY_ORDER.index(b.severity)
    return a.name_evidence == "title" and b.name_evidence != "title"
