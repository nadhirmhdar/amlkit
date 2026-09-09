"""UK Sanctions List (UKSL) adapter.

The UKSL is published by the UK Foreign, Commonwealth & Development Office
(FCDO) and is the authoritative UK sanctions screening list since January 2026.
It replaces the old OFSI Consolidated List.

Data is freely available in XML format under the Open Government Licence v3.0.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Iterator

from .base import AdapterError, SourceEntity, fetch_with_retry

URL = "https://sanctionslist.fcdo.gov.uk/docs/UK-Sanctions-List.xml"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"


class UKSanctionsAdapter:
    """Loads UK Sanctions List from gov.uk."""

    def __init__(self) -> None:
        self.key = "uk_sanctions"
        self.title = "UK Sanctions List (UKSL)"
        self.publisher = "UK Foreign, Commonwealth & Development Office"
        self.source_url = URL
        self.licence = "Open Government Licence v3.0"
        self.is_mandatory = False  # Not mandatory under UAE law

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

        # The UK sanctions list uses a namespace
        # Try to detect namespace from root tag
        ns = ""
        if root.tag.startswith("{"):
            ns = root.tag.split("}")[0] + "}"

        seen = 0

        # Find all Designation elements
        for designation in root.iter(f"{ns}Designation"):
            seen += 1
            uid = ""
            uid_el = designation.find(f"{ns}UniqueID")
            if uid_el is not None and uid_el.text:
                uid = uid_el.text.strip()
            if not uid:
                # Try alternative ID fields
                uid_el = designation.find(f"{ns}OFSIGroupID")
                if uid_el is not None and uid_el.text:
                    uid = uid_el.text.strip()
                else:
                    uid = f"UK-{seen}"

            # Determine if individual or entity
            ind_names = designation.find(f"{ns}Names")
            schema_type = "Person"
            caption = ""
            names = []
            countries = []
            birth_date = None
            gender = None
            identifiers = []

            if ind_names is not None:
                for name_el in ind_names.findall(f"{ns}Name"):
                    name_type = ""
                    name_type_el = name_el.find(f"{ns}NameType")
                    if name_type_el is not None and name_type_el.text:
                        name_type = name_type_el.text.strip()

                    # Build full name from components
                    parts = []
                    for component_tag in ["Name1", "Name2", "Name3", "Name4", "Name5", "Name6"]:
                        comp = name_el.find(f"{ns}{component_tag}")
                        if comp is not None and comp.text and comp.text.strip():
                            parts.append(comp.text.strip())

                    full_name = " ".join(parts)
                    if not full_name:
                        continue

                    if name_type in ("Primary Name", "Primary name", "") and not caption:
                        caption = full_name
                    else:
                        names.append(full_name)

            if not caption and names:
                caption = names.pop(0)
            if not caption:
                continue

            # Determine type from GroupTypeDescription
            group_type = designation.find(f"{ns}GroupTypeDescription")
            if group_type is not None and group_type.text:
                gt = group_type.text.strip().lower()
                if "entity" in gt or "ship" in gt:
                    schema_type = "Organization"

            # Individual details
            ind_details = designation.find(f"{ns}IndividualDetails")
            if ind_details is not None:
                schema_type = "Person"
                dob_el = ind_details.find(f"{ns}DOBs")
                if dob_el is not None:
                    for dob in dob_el.findall(f"{ns}DOB"):
                        date_text = dob.text if dob.text else ""
                        if not date_text:
                            date_text = dob.findtext(f"{ns}DOB") or ""
                        if date_text.strip():
                            birth_date = date_text.strip()
                            break

                gender_el = ind_details.find(f"{ns}Gender")
                if gender_el is not None and gender_el.text:
                    gender = gender_el.text.strip()

                nat_el = ind_details.find(f"{ns}Nationalities")
                if nat_el is not None:
                    for nat in nat_el.findall(f"{ns}Nationality"):
                        country = nat.text if nat.text else ""
                        if not country:
                            country = nat.findtext(f"{ns}Nationality") or ""
                        if country.strip() and country.strip() not in countries:
                            countries.append(country.strip())

                # Passport numbers
                passport_el = ind_details.find(f"{ns}PassportDetails")
                if passport_el is not None:
                    for pp in passport_el.findall(f"{ns}PassportDetail"):
                        pp_num = pp.findtext(f"{ns}PassportNumber")
                        if pp_num and pp_num.strip():
                            identifiers.append(("passport", pp_num.strip()))

            # Addresses for country info
            addresses = designation.find(f"{ns}Addresses")
            if addresses is not None:
                for addr in addresses.findall(f"{ns}Address"):
                    country = addr.findtext(f"{ns}Country")
                    if country and country.strip() and country.strip() not in countries:
                        countries.append(country.strip())

            # Sanctions regime
            programs = []
            regime = designation.find(f"{ns}UKSanctionsListRef")
            if regime is not None and regime.text:
                programs.append(regime.text.strip())
            regime2 = designation.find(f"{ns}RegimeName")
            if regime2 is not None and regime2.text:
                programs.append(regime2.text.strip())

            raw = {
                "uk_unique_id": uid,
                "group_type": group_type.text.strip() if group_type is not None and group_type.text else None,
            }

            yield SourceEntity(
                source_id=f"UK-{uid}",
                schema_type=schema_type,
                caption=caption,
                names=names[:20],  # Limit aliases
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
            raise AdapterError(f"{self.key}: parsed 0 designations from UK Sanctions List")
