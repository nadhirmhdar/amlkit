"""EU Consolidated Sanctions List adapter.

ACCESS TOKEN
------------
The Commission serves the Financial Sanctions Files behind a per-user token
obtained by registering with the FSF distribution service. The default below
is the long-standing token the Commission publishes in its own documentation
and examples, which is why this adapter works out of the box -- but it is not
this deployment's token, and the Commission can rotate or rate-limit it
without notice.

Before relying on the EU list in production, register at
https://webgate.ec.europa.eu/fsd/fsf and set AMLKIT_EU_FSF_TOKEN. It is read
at fetch time rather than import time so the deployment can rotate it without
a rebuild.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Iterator

import httpx

from .base import AdapterError, SourceEntity

BASE_URL = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
DEFAULT_TOKEN = "dG9rZW4tMjAxNy0xMS0xMw"
ENV_TOKEN = "AMLKIT_EU_FSF_TOKEN"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"


def list_url() -> str:
    token = os.environ.get(ENV_TOKEN, "").strip() or DEFAULT_TOKEN
    return f"{BASE_URL}?token={token}"


# Kept for callers that imported the module-level constant.
URL = list_url()


class EUSanctionsAdapter:
    """Loads EU Consolidated Sanctions list from webgate.ec.europa.eu."""

    def __init__(self) -> None:
        self.key = "eu_sanctions"
        self.title = "EU Consolidated Sanctions List"
        self.publisher = "European Union"
        # Resolved per instance, not at import, so a token set after startup
        # (or in a test) is actually used.
        self.source_url = list_url()
        self.licence = "Public Domain"
        self.is_mandatory = False

    def fetch(self) -> bytes:
        try:
            r = httpx.get(
                self.source_url,
                timeout=15,
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
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise AdapterError(f"{self.key}: XML parse failed - {exc}") from exc

        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        seen = 0
        for entry in root.findall(f".//{ns}sanctionEntity"):
            seen += 1
            logical_id = entry.get("logicalId") or ""
            if not logical_id:
                continue

            # Check entity type (individual or legal entity)
            # Typically represented by elements or attributes like <subjectType code="individual"/>
            subj_type = entry.find(f"{ns}subjectType")
            subj_code = subj_type.get("code") if subj_type is not None else ""
            
            schema_type = "Person" if subj_code.lower() == "individual" else "Organization"

            # Gather all WholeNames
            names = []
            caption = f"EU-ENT-{logical_id}"
            first_alias = True
            
            for alias in entry.findall(f".//{ns}nameAlias"):
                whole_name = alias.findtext(f"{ns}wholeName")
                if whole_name and whole_name.strip():
                    name_str = whole_name.strip()
                    if first_alias:
                        caption = name_str
                        first_alias = False
                    elif name_str not in names:
                        names.append(name_str)

            countries = []
            for cit in entry.findall(f".//{ns}citizenship"):
                country = cit.findtext(f"{ns}countryDescription") or cit.findtext(f"{ns}region")
                if country and country.strip() and country.strip() not in countries:
                    countries.append(country.strip())

            # Birthdate
            birth_date = None
            dob_el = entry.find(f".//{ns}birthdate")
            if dob_el is not None:
                birth_date = dob_el.findtext(f"{ns}calendarDate") or dob_el.findtext(f"{ns}year")

            # Gender
            gender = entry.findtext(f"{ns}gender")

            # Regulations/Programs
            programs = []
            for reg in entry.findall(f".//{ns}regulation"):
                reg_num = reg.findtext(f"{ns}regulationNumber")
                reg_type = reg.get("regulationType")
                if reg_num:
                    programs.append(f"{reg_type or 'REG'}-{reg_num}")

            # Identifiers
            identifiers = []
            for doc in entry.findall(f".//{ns}identificationDoc"):
                doc_num = doc.findtext(f"{ns}number")
                doc_type = doc.findtext(f"{ns}typeDescription") or doc.get("docType") or ""
                if doc_num and doc_num.strip():
                    kind = "passport" if "passport" in doc_type.lower() else "id"
                    identifiers.append((kind, doc_num.strip()))

            raw = {
                "eu_logical_id": logical_id,
                "remarks": entry.findtext(f"{ns}remark"),
            }

            yield SourceEntity(
                source_id=f"EU-{logical_id}",
                schema_type=schema_type,
                caption=caption,
                names=names,
                countries=countries,
                birth_date=birth_date,
                gender=gender,
                topics=["sanction"],
                programs=programs,
                identifiers=identifiers,
                listed_at=None,
                raw=raw,
            )

        if seen == 0:
            raise AdapterError(f"{self.key}: parsed 0 entities")
