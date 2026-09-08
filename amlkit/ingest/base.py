"""Source adapter boundary.

This interface is the project's commercial hedge, and it is worth being
explicit about why it exists.

OpenSanctions publishes an excellent consolidated dataset -- including the UAE
Local Terrorist List, already parsed and deduplicated -- free for
non-commercial use. It was by far the fastest way to a working system. But
there are no licence exemptions for commercial users, so selling this tool
meant that data had to be either licensed or replaced.

Every source normalises into one `SourceEntity` shape behind one interface,
so replacing it was a configuration change rather than a rewrite. That swap
has now happened: the shipped refresh path reads primary sources only --
`eocn.py` (UAE), `un.py`, `ofac.py`, `uk.py`, `eu.py`, `cia.py` -- all of them
free to redistribute commercially. `opensanctions.py` stays behind the same
interface for non-commercial and comparison use.

The boundary earned its keep exactly once, and that was enough: retrofitting
it later would have meant touching matching, storage and reporting at once.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

from ..names.arabic import blocking_keys, canonical_key, has_arabic_script


@dataclass(slots=True)
class SourceEntity:
    """One sanctioned/PEP entity, normalised across all sources.

    Field names deliberately follow the FollowTheMoney vocabulary so that
    OpenSanctions records pass through untranslated and primary-source records
    are mapped onto a schema that is already an industry convention.
    """

    source_id: str
    schema_type: str                       # Person | Company | Organization | Vessel
    caption: str
    names: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    birth_date: str | None = None
    gender: str | None = None
    topics: list[str] = field(default_factory=list)
    # Sanction programme identifiers. The only way to tell a proliferation
    # designation from a terrorism one, which Law 10/2025 makes distinct
    # offences.
    programs: list[str] = field(default_factory=list)
    identifiers: list[tuple[str, str]] = field(default_factory=list)
    listed_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def all_names(self) -> list[str]:
        """Primary caption plus aliases, deduplicated, order preserved."""
        seen: dict[str, None] = {}
        for n in [self.caption, *self.names]:
            n = (n or "").strip()
            if n:
                seen.setdefault(n, None)
        return list(seen)

    def name_rows(self) -> list[tuple[str, str, str, str]]:
        """(name, name_type, canonical_key, script) for storage."""
        rows = []
        for i, n in enumerate(self.all_names()):
            rows.append(
                (
                    n,
                    "primary" if i == 0 else "alias",
                    canonical_key(n),
                    "arabic" if has_arabic_script(n) else "latin",
                )
            )
        return rows

    def tokens(self) -> set[str]:
        keys: set[str] = set()
        for n in self.all_names():
            keys |= blocking_keys(n)
        return keys

    def raw_json(self) -> str:
        return json.dumps(self.raw, ensure_ascii=False, default=str)


class SourceAdapter(Protocol):
    """Contract every data source must satisfy."""

    key: str            # stable dataset key, e.g. 'ae_local_terrorists'
    title: str
    publisher: str
    source_url: str
    licence: str
    is_mandatory: bool  # required by UAE law rather than merely useful

    def fetch(self) -> bytes:
        """Download the raw payload from the source."""

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        """Convert the raw payload into normalised entities."""


class AdapterError(RuntimeError):
    """Raised when a source cannot be fetched or parsed.

    Deliberately loud. A silently-failing sanctions feed is worse than no feed
    at all, because the screening log will show green while coverage has
    quietly lapsed -- exactly the failure mode the 24-hour update rule exists
    to prevent.
    """


_DEFAULT_USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"


def fetch_with_retry(
    adapter_key: str,
    url: str,
    *,
    timeout: float = 180,
    user_agent: str = _DEFAULT_USER_AGENT,
    max_attempts: int = 3,
) -> bytes:
    """GET *url* with exponential-backoff retries on transient errors.

    Separates error categories so callers receive actionable messages:
    - Timeout / connectivity → retried, then AdapterError naming the URL
    - Rate-limit (429)      → retried with longer back-off
    - Server error (5xx)    → retried
    - Auth error (401/403)  → AdapterError immediately (retrying is pointless)
    - Other HTTP errors     → AdapterError immediately

    Replacing per-adapter try/except blocks with this helper means every
    source gets the same retry discipline and the same error vocabulary.
    """
    import time

    import httpx

    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            r = httpx.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
            )
        except httpx.TimeoutException as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise AdapterError(
                f"{adapter_key}: timed out after {timeout}s fetching {url}"
            ) from exc
        except httpx.ConnectError as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise AdapterError(
                f"{adapter_key}: connection error (DNS / TLS / refused) — {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AdapterError(f"{adapter_key}: fetch failed — {exc}") from exc

        if r.status_code in (401, 403):
            raise AdapterError(
                f"{adapter_key}: access denied ({r.status_code}) from {url}"
            )
        if r.status_code == 429:
            wait = min(10 * (attempt + 1), 60)
            if attempt < max_attempts - 1:
                time.sleep(wait)
                continue
            raise AdapterError(
                f"{adapter_key}: rate-limited (HTTP 429) — try again later"
            )
        if r.status_code >= 500:
            last_exc = Exception(f"HTTP {r.status_code}")
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise AdapterError(
                f"{adapter_key}: server error ({r.status_code}) from {url} "
                f"after {attempt + 1} attempt(s)"
            )
        try:
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterError(
                f"{adapter_key}: unexpected HTTP {r.status_code} from {url}"
            ) from exc

        if not r.content:
            raise AdapterError(f"{adapter_key}: {url} returned an empty body")
        return r.content

    raise AdapterError(
        f"{adapter_key}: fetch failed after {max_attempts} attempt(s) — {last_exc}"
    )
