"""Interpol Red Notices adapter.

Fetches the Interpol public API paginated JSON endpoint and yields one
SourceEntity per Red Notice. The API returns ~6500 notices across ~40 pages.
"""

from __future__ import annotations

import json
from typing import Iterator

import httpx

from .base import AdapterError, SourceEntity

BASE_URL = "https://ws-public.interpol.int/notices/v1/red"
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"
PAGE_SIZE = 160


class InterpolRedNoticeAdapter:

    def __init__(self) -> None:
        self.key = "interpol_red_notices"
        self.title = "Interpol Red Notices"
        self.publisher = "INTERPOL"
        self.source_url = BASE_URL
        self.licence = "Public"
        self.is_mandatory = False

    def fetch(self) -> bytes:
        all_notices: list[dict] = []
        url = f"{BASE_URL}?page=1&resultPerPage={PAGE_SIZE}"

        while url:
            try:
                r = httpx.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
                r.raise_for_status()
            except httpx.HTTPError as exc:
                raise AdapterError(
                    f"{self.key}: fetch failed — {exc}"
                ) from exc

            data = r.json()
            notices = data.get("_embedded", {}).get("notices", [])
            all_notices.extend(notices)

            next_link = data.get("_links", {}).get("next", {}).get("href")
            if next_link:
                if next_link.startswith("/"):
                    url = f"https://ws-public.interpol.int{next_link}"
                else:
                    url = next_link
            else:
                url = None

        return json.dumps(all_notices).encode("utf-8")

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        notices = json.loads(payload)
        if not notices:
            raise AdapterError(f"{self.key}: parsed 0 entities")

        for notice in notices:
            entity_id = notice.get("entity_id", "")
            if not entity_id:
                continue

            forename = (notice.get("forename") or "").strip()
            name = (notice.get("name") or "").strip()
            caption = f"{forename} {name}".strip() or f"INTERPOL-{entity_id}"

            countries = notice.get("nationalities") or []

            birth_date = None
            raw_dob = notice.get("date_of_birth")
            if raw_dob:
                birth_date = raw_dob.replace("/", "-")

            programs = []
            for warrant in notice.get("arrest_warrants") or []:
                country_id = warrant.get("issuing_country_id")
                if country_id and country_id not in programs:
                    programs.append(country_id)

            yield SourceEntity(
                source_id=f"interpol/{entity_id}",
                schema_type="Person",
                caption=caption,
                names=[],
                countries=countries,
                birth_date=birth_date,
                gender=None,
                topics=["crime", "fugitive", "red-notice"],
                programs=programs,
                identifiers=[],
                listed_at=None,
                raw=notice,
            )
