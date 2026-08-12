"""Source adapter boundary.

This interface is the project's commercial hedge, and it is worth being
explicit about why it exists.

OpenSanctions publishes an excellent consolidated dataset -- including the UAE
Local Terrorist List, already parsed and deduplicated -- free for
non-commercial use. It is by far the fastest way to a working system. But
there are no licence exemptions for commercial users, so if this tool is ever
sold, that data has to be either licensed or replaced.

Every source therefore normalises into one `SourceEntity` shape behind one
interface. Swapping the OpenSanctions adapter for direct primary-source
adapters (OFAC, UN, EU, UK, EOCN -- all public domain and free to
redistribute) is then a configuration change, not a rewrite. Retrofitting this
boundary later would mean touching matching, storage and reporting at once.
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
