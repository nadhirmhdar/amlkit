"""OFAC SDN List adapter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterator

from .base import AdapterError, SourceEntity, fetch_with_retry

URL = "https://www.treasury.gov/ofac/downloads/sdn.xml"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"


class OFACSDNAdapter:
    """Loads OFAC SDN list from treasury.gov."""

    def __init__(self) -> None:
        self.key = "ofac_sdn"
        self.title = "OFAC SDN List"
        self.publisher = "US Office of Foreign Assets Control"
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
        # Strip xmlns if present to make xpath queries simpler
        # OFAC sdn.xml typically does not use namespaces or uses 'http://tempuri.org/sdn.xsd'
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise AdapterError(f"{self.key}: XML parse failed - {exc}") from exc

        # Detect and clean namespace if present
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        seen = 0
        for entry in root.findall(f".//{ns}sdnEntry"):
            seen += 1
            uid = entry.findtext(f"{ns}uid") or ""
            if not uid:
                continue

            sdn_type = entry.findtext(f"{ns}sdnType") or "Individual"
            
            # Map type to schema_type
            schema_map = {
                "Individual": "Person",
                "Entity": "Organization",
                "Vessel": "Vessel",
                "Aircraft": "Airplane",
            }
            schema_type = schema_map.get(sdn_type, "Organization")

            first_name = entry.findtext(f"{ns}firstName") or ""
            last_name = entry.findtext(f"{ns}lastName") or ""
            caption = f"{first_name} {last_name}".strip() if first_name else last_name

            names = [caption]
            for aka in entry.findall(f".//{ns}aka"):
                aka_first = aka.findtext(f"{ns}firstName") or ""
                aka_last = aka.findtext(f"{ns}lastName") or ""
                aka_name = f"{aka_first} {aka_last}".strip() if aka_first else aka_last
                if aka_name and aka_name not in names:
                    names.append(aka_name)

            countries = []
            # Gather countries from addresses
            for addr in entry.findall(f".//{ns}address"):
                country = addr.findtext(f"{ns}country")
                if country and country.strip() and country.strip() not in countries:
                    countries.append(country.strip())

            # DOB (usually for individuals)
            birth_date = None
            dob_el = entry.find(f".//{ns}dateOfBirthItem")
            if dob_el is not None:
                birth_date = dob_el.findtext(f"{ns}dateOfBirth")

            # Gender is not explicitly structured in OFAC SDN, but raw has it sometimes in remarks.
            gender = None

            # Programs
            programs = []
            for prog in entry.findall(f".//{ns}program"):
                if prog.text:
                    programs.append(prog.text.strip())

            # Identifiers (passports, tax IDs, etc.)
            identifiers = []
            for id_node in entry.findall(f".//{ns}id"):
                id_type = id_node.findtext(f"{ns}idType") or ""
                id_num = id_node.findtext(f"{ns}idNumber") or ""
                if id_num and id_num.strip():
                    kind = "passport" if "passport" in id_type.lower() else "id"
                    identifiers.append((kind, id_num.strip()))

            raw = {
                "ofac_sdn_type": sdn_type,
                "remarks": entry.findtext(f"{ns}remarks"),
                "title": entry.findtext(f"{ns}title"),
            }

            yield SourceEntity(
                source_id=f"OFAC-{uid}",
                schema_type=schema_type,
                caption=caption,
                names=names[1:],
                countries=countries,
                birth_date=birth_date,
                gender=gender,
                topics=["sanction"],
                programs=programs,
                identifiers=identifiers,
                listed_at=None, # OFAC SDN XML does not have listed_at date directly on sdnEntry
                raw=raw,
            )

        if seen == 0:
            raise AdapterError(f"{self.key}: parsed 0 entities")
