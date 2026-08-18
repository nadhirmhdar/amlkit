"""OpenSanctions adapter (FollowTheMoney JSON-lines).

LICENCE WARNING
---------------
OpenSanctions data is free for non-commercial use only. There are no
exemptions for commercial users. While this adapter is the active source the
tool must not be sold or used to provide a paid service. Swap to the
primary-source adapters in `un.py` / `ofac.py` / `eocn.py` before any
commercial use -- that is precisely why the adapter boundary exists.
"""

from __future__ import annotations

import json
from typing import Iterator

import httpx

from .base import AdapterError, SourceEntity

BASE = "https://data.opensanctions.org/datasets/latest"

# A FtM export interleaves screenable targets with the supporting records they
# reference (the sanction programme, an address, a passport). Only these
# schemas are people or organisations that can themselves be screened; the
# rest are attributes reached via reference and would create phantom alerts if
# indexed as targets in their own right.
SCREENABLE = {
    "Person", "Company", "Organization", "LegalEntity",
    "Vessel", "Airplane", "Trust", "PublicBody",
}

USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"


class OpenSanctionsAdapter:
    """Loads any OpenSanctions dataset by key."""

    def __init__(
        self,
        dataset: str = "ae_local_terrorists",
        title: str = "UAE Local Terrorist List",
        is_mandatory: bool = True,
    ) -> None:
        self.dataset = dataset
        self.key = dataset
        self.title = title
        self.publisher = "OpenSanctions"
        self.source_url = f"{BASE}/{dataset}/entities.ftm.json"
        self.licence = "CC-BY-NC 4.0 - NON-COMMERCIAL USE ONLY"
        self.is_mandatory = is_mandatory

    def fetch(self) -> bytes:
        try:
            r = httpx.get(
                self.source_url,
                timeout=180,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterError(f"{self.key}: fetch failed - {exc}") from exc
        if not r.content:
            raise AdapterError(f"{self.key}: source returned an empty body")
        return r.content

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        text = payload.decode("utf-8", errors="replace")
        seen = 0
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("schema") not in SCREENABLE:
                continue
            seen += 1
            props = rec.get("properties", {}) or {}
            yield SourceEntity(
                source_id=rec["id"],
                schema_type=rec["schema"],
                caption=rec.get("caption") or _first(props, "name") or rec["id"],
                names=_collect(props, "name", "alias", "previousName", "weakAlias"),
                countries=_collect(props, "country", "nationality", "jurisdiction"),
                birth_date=_first(props, "birthDate"),
                gender=_first(props, "gender"),
                topics=props.get("topics", []) or [],
                programs=_collect(props, "programId", "program"),
                identifiers=_identifiers(props),
                listed_at=rec.get("first_seen"),
                raw=rec,
            )
        if seen == 0:
            # Schema drift or a truncated download. Failing loudly here is the
            # control that stops a lapsed feed from looking healthy.
            raise AdapterError(
                f"{self.key}: parsed 0 screenable entities - source format may have changed"
            )


def _collect(props: dict, *keys: str) -> list[str]:
    out: list[str] = []
    for k in keys:
        for v in props.get(k, []) or []:
            if v and v not in out:
                out.append(str(v))
    return out


def _first(props: dict, key: str) -> str | None:
    vals = props.get(key) or []
    return str(vals[0]) if vals else None


# Identifier types carry high match weight (LEI/BIC at 0.95 in the
# OpenSanctions model) because an exact identifier hit is far stronger
# evidence than any name similarity.
_ID_FIELDS = {
    "leiCode": "lei",
    "swiftBic": "swift",
    "innCode": "tax",
    "ogrnCode": "tax",
    "taxNumber": "tax",
    "registrationNumber": "registration",
    "passportNumber": "passport",
    "idNumber": "id",
    "imoNumber": "imo",
    "cryptoWallet": "crypto",
}


def _identifiers(props: dict) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for field, kind in _ID_FIELDS.items():
        for v in props.get(field, []) or []:
            if v:
                out.append((kind, str(v).strip()))
    return out


# Convenience constructors for the datasets this project actually uses.
def uae_local_terrorists() -> OpenSanctionsAdapter:
    """The UAE Local Terrorist List -- mandatory under UAE law."""
    return OpenSanctionsAdapter("ae_local_terrorists", "UAE Local Terrorist List", True)


def un_sanctions() -> OpenSanctionsAdapter:
    """UN Security Council Consolidated List -- mandatory under UAE law."""
    return OpenSanctionsAdapter("un_sc_sanctions", "UN Security Council Consolidated List", True)


def global_sanctions() -> OpenSanctionsAdapter:
    """Consolidated global sanctions (OFAC, EU, UK and others)."""
    return OpenSanctionsAdapter("sanctions", "Consolidated Global Sanctions", False)


def peps() -> OpenSanctionsAdapter:
    """Politically exposed persons. Not itself a sanctions list; drives EDD."""
    return OpenSanctionsAdapter("peps", "Politically Exposed Persons", False)


def cia_world_leaders() -> OpenSanctionsAdapter:
    """CIA World Leaders (PEP List) -- public domain and free to use commercially."""
    return OpenSanctionsAdapter("us_cia_world_leaders", "CIA World Leaders (PEPs)", False)
