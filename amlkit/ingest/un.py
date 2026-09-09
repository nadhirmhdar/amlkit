"""UN Consolidated Sanctions List adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterator

from .base import AdapterError, SourceEntity, fetch_with_retry

URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"


class UNSanctionsAdapter:
    """Loads UN Consolidated Sanctions list from scsanctions.un.org."""

    def __init__(self) -> None:
        self.key = "un_consolidated"
        self.title = "UN Consolidated Sanctions List"
        self.publisher = "United Nations Security Council"
        self.source_url = URL
        self.licence = "Public Domain"
        self.is_mandatory = True

    def fetch(self) -> bytes:
        payload = fetch_with_retry(self.key, self.source_url, user_agent=USER_AGENT)
        if payload.lstrip()[:1] != b"<":
            raise AdapterError(
                f"{self.key}: response is not XML (got {payload[:60]!r})"
            )
        return payload

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise AdapterError(f"{self.key}: XML parse failed - {exc}") from exc

        seen = 0
        # Parse individuals
        for ind in root.findall(".//INDIVIDUAL"):
            seen += 1
            source_id = ind.findtext("DATAID") or ""
            if not source_id:
                continue

            first_name = ind.findtext("FIRST_NAME") or ""
            second_name = ind.findtext("SECOND_NAME") or ""
            third_name = ind.findtext("THIRD_NAME") or ""
            last_name = ind.findtext("LAST_NAME") or ""
            
            parts = [p.strip() for p in [first_name, second_name, third_name, last_name] if p.strip()]
            caption = " ".join(parts) if parts else f"UN-IND-{source_id}"

            names = [caption]
            for alias in ind.findall(".//INDIVIDUAL_ALIAS"):
                alias_name = alias.findtext("ALIAS_NAME")
                if alias_name and alias_name.strip():
                    names.append(alias_name.strip())

            countries = []
            for doc in ind.findall(".//INDIVIDUAL_DOCUMENT"):
                country = doc.findtext("COUNTRY")
                if country and country.strip() and country.strip() not in countries:
                    countries.append(country.strip())
            for nat in ind.findall(".//NATIONALITY"):
                country = nat.findtext("COUNTRY")
                if country and country.strip() and country.strip() not in countries:
                    countries.append(country.strip())

            birth_date = None
            dob_el = ind.find(".//INDIVIDUAL_DATE_OF_BIRTH")
            if dob_el is not None:
                birth_date = dob_el.findtext("DATE") or dob_el.findtext("YEAR")

            gender = ind.findtext("GENDER")

            programs = []
            ref_type = ind.findtext("REFERENCE_NUMBER")
            if ref_type:
                programs.append(ref_type)

            identifiers = []
            for doc in ind.findall(".//INDIVIDUAL_DOCUMENT"):
                doc_num = doc.findtext("NUMBER")
                doc_type = doc.findtext("TYPE_OF_DOCUMENT")
                if doc_num and doc_num.strip():
                    kind = "passport" if doc_type and "passport" in doc_type.lower() else "id"
                    identifiers.append((kind, doc_num.strip()))

            raw = {
                "un_list_type": "individual",
                "reference_number": ref_type,
                "comments": ind.findtext("COMMENTS1"),
            }

            yield SourceEntity(
                source_id=f"UN-{source_id}",
                schema_type="Person",
                caption=caption,
                names=names[1:],
                countries=countries,
                birth_date=birth_date,
                gender=gender,
                topics=["sanction"],
                programs=programs,
                identifiers=identifiers,
                listed_at=ind.findtext("LISTED_ON"),
                raw=raw,
            )

        # Parse entities
        for ent in root.findall(".//ENTITY"):
            seen += 1
            source_id = ent.findtext("DATAID") or ""
            if not source_id:
                continue

            caption = ent.findtext("FIRST_NAME") or f"UN-ENT-{source_id}"
            names = [caption]
            for alias in ent.findall(".//ENTITY_ALIAS"):
                alias_name = alias.findtext("ALIAS_NAME")
                if alias_name and alias_name.strip():
                    names.append(alias_name.strip())

            countries = []
            for country_el in ent.findall(".//COUNTRY"):
                country = country_el.text
                if country and country.strip() and country.strip() not in countries:
                    countries.append(country.strip())

            programs = []
            ref_type = ent.findtext("REFERENCE_NUMBER")
            if ref_type:
                programs.append(ref_type)

            raw = {
                "un_list_type": "entity",
                "reference_number": ref_type,
                "comments": ent.findtext("COMMENTS1"),
            }

            yield SourceEntity(
                source_id=f"UN-{source_id}",
                schema_type="Organization",
                caption=caption,
                names=names[1:],
                countries=countries,
                birth_date=None,
                gender=None,
                topics=["sanction"],
                programs=programs,
                identifiers=[],
                listed_at=ent.findtext("LISTED_ON"),
                raw=raw,
            )

        if seen == 0:
            raise AdapterError(f"{self.key}: parsed 0 entities")
