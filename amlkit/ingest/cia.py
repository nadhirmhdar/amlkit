"""CIA World Leaders -- direct ingestion, for PEP screening.

WHY THIS ADAPTER EXISTS
-----------------------
Same reason as `eocn.py`: the project previously took this list through
OpenSanctions (`us_cia_world_leaders`), whose distribution is CC-BY-NC and so
cannot be used by a product that is sold. The underlying publication is a work
of the US federal government and is in the public domain, so going to the
source removes the licence constraint entirely rather than arguing about it.

WHAT THIS IS AND IS NOT
-----------------------
This is a *baseline* PEP source, not a comprehensive one. It covers sitting
heads of state, ministers, central bank governors and ambassadors for ~199
countries -- roughly five thousand people. It does NOT cover former officials,
their relatives, or close associates, all three of which UAE CDD obligations
also reach. A firm relying on this alone has partial PEP coverage, and the
tool should say so rather than imply otherwise.

It is registered as an optional source: a PEP hit changes the customer's risk
rating and required approvals, but unlike a sanctions hit it does not carry a
freeze-and-report duty, so a failed refresh must not block the pipeline the
way a mandatory sanctions list does.

SHAPE OF THE SOURCE
-------------------
The site is a static Gatsby build, which means every country page has a
matching JSON document that holds exactly the data the page renders, with no
HTML to parse:

    /page-data/foreign-governments/<slug>/page-data.json
        -> result.data.page = {code, country, date_updated, leaders: [...]}

The country list comes from the site's own sitemap rather than the index page,
because the index lazy-loads and only ships a dozen countries in its HTML.
"""

from __future__ import annotations

import json
import re
from typing import Iterator

import httpx

from .base import AdapterError, SourceEntity

SITEMAP_URL = "https://www.cia.gov/resources/world-leaders/sitemap/sitemap-index.xml"
PAGE_DATA_URL = (
    "https://www.cia.gov/resources/world-leaders/page-data/foreign-governments/"
    "{slug}/page-data.json"
)
USER_AGENT = "amlkit/0.1 (UAE AML screening; compliance tooling)"

_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_COUNTRY_PATH = re.compile(r"/foreign-governments/([a-z0-9-]+)/?$")

# A handful of country pages failing is normal churn on a site of this size --
# a slug renamed between the sitemap build and the fetch, a transient 5xx. A
# large fraction failing means something structural broke, and quietly
# ingesting 40% of the world's leaders as if that were the whole list is worse
# than refusing to ingest at all.
MAX_FAILURE_RATIO = 0.10


class CIAWorldLeadersAdapter:
    """Politically exposed persons, from the CIA's World Leaders publication."""

    def __init__(self) -> None:
        self.key = "us_cia_world_leaders"
        self.title = "CIA World Leaders (PEPs)"
        self.publisher = "US Central Intelligence Agency"
        self.source_url = "https://www.cia.gov/resources/world-leaders/"
        # 17 U.S.C. section 105: works of the US federal government are not
        # subject to copyright protection. Free to redistribute, commercially
        # included -- which is the point of fetching it here rather than
        # through a non-commercial aggregator.
        self.licence = "Public Domain (US Government work)"
        self.is_mandatory = False

    # -- fetch ------------------------------------------------------------

    def fetch(self) -> bytes:
        """Return one JSON document per country, newline-delimited.

        Assembling the whole source into a single payload keeps the adapter
        interface intact (fetch produces bytes, parse consumes them) and means
        the parser can be tested against a captured payload with no network.
        """
        with httpx.Client(
            timeout=60,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            slugs = self._country_slugs(client)
            if not slugs:
                raise AdapterError(
                    f"{self.key}: sitemap listed no country pages - site structure "
                    "may have changed"
                )

            documents: list[bytes] = []
            failures: list[str] = []
            for slug in slugs:
                try:
                    response = client.get(PAGE_DATA_URL.format(slug=slug))
                    response.raise_for_status()
                    page = response.json()["result"]["data"]["page"]
                except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                    failures.append(f"{slug} ({type(exc).__name__})")
                    continue
                documents.append(json.dumps(page, ensure_ascii=False).encode("utf-8"))

        if len(failures) > len(slugs) * MAX_FAILURE_RATIO:
            raise AdapterError(
                f"{self.key}: {len(failures)} of {len(slugs)} country pages failed "
                f"- refusing a partial PEP list. First few: {failures[:5]}"
            )
        return b"\n".join(documents)

    def _country_slugs(self, client: httpx.Client) -> list[str]:
        try:
            index = client.get(SITEMAP_URL)
            index.raise_for_status()
        except httpx.HTTPError as exc:
            raise AdapterError(f"{self.key}: sitemap index fetch failed - {exc}") from exc

        slugs: list[str] = []
        for sitemap_url in _LOC.findall(index.text):
            try:
                sitemap = client.get(sitemap_url)
                sitemap.raise_for_status()
            except httpx.HTTPError as exc:
                raise AdapterError(f"{self.key}: sitemap fetch failed - {exc}") from exc
            for url in _LOC.findall(sitemap.text):
                match = _COUNTRY_PATH.search(url)
                if not match:
                    continue
                slug = match.group(1)
                # The listing page itself matches the same URL shape.
                if slug != "foreign-governments" and slug not in slugs:
                    slugs.append(slug)
        return slugs

    # -- parse ------------------------------------------------------------

    def parse(self, payload: bytes) -> Iterator[SourceEntity]:
        seen = 0
        for line in payload.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                page = json.loads(line)
            except json.JSONDecodeError:
                continue

            country = (page.get("country") or "").strip()
            code = (page.get("code") or "").strip()
            updated = (page.get("date_updated") or "").strip() or None

            used_ids: set[str] = set()
            for leader in page.get("leaders") or []:
                entity = _leader_to_entity(leader, country, code, updated, used_ids)
                if entity is None:
                    continue
                seen += 1
                yield entity

        if seen == 0:
            raise AdapterError(
                f"{self.key}: parsed 0 leaders - source format may have changed"
            )


def _leader_to_entity(
    leader: dict,
    country: str,
    code: str,
    updated: str | None,
    used_ids: set[str],
) -> SourceEntity | None:
    name = (leader.get("name") or "").strip()
    if not name or name in {"NA", "N/A", "-", "Vacant", "vacant"}:
        return None

    title = (leader.get("title") or "").strip()
    honorific = (leader.get("honorific") or "").strip()

    source_id = f"CIA-{code or 'XX'}-{_slug(name)}"
    # Two people with the same name in one government is rare but real, and a
    # duplicate source_id would collapse them into one entity.
    if source_id in used_ids:
        suffix = 2
        while f"{source_id}-{suffix}" in used_ids:
            suffix += 1
        source_id = f"{source_id}-{suffix}"
    used_ids.add(source_id)

    names = []
    if honorific and f"{honorific} {name}" != name:
        names.append(f"{honorific} {name}")

    return SourceEntity(
        source_id=source_id,
        schema_type="Person",
        # `country` is the plain English country name, deliberately without the
        # `code` beside it: the CIA publishes FIPS 10-4 codes, not ISO 3166,
        # and the two disagree in ways that would be actively harmful here --
        # FIPS "AG" is Algeria while ISO "AG" is Antigua and Barbuda. Since
        # scorer.py uses this list to apply a country_mismatch PENALTY, a wrong
        # code would suppress real matches. The FIPS code stays in `raw`.
        caption=name,
        names=names,
        countries=[country] if country else [],
        birth_date=None,      # not published
        gender=None,          # not published
        # role.pep is the FollowTheMoney topic the matcher and queries.py both
        # key PEP classification off.
        topics=["role.pep"],
        programs=[],          # a PEP is not designated under any programme
        identifiers=[],
        listed_at=updated,
        raw={
            "source": "CIA World Leaders",
            "country": country,
            "fips_code": code,
            "title": title,
            "honorific": honorific,
            "page_updated": updated,
        },
    )


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").upper()[:60]


def cia_world_leaders() -> CIAWorldLeadersAdapter:
    """Baseline PEP coverage, from the primary source."""
    return CIAWorldLeadersAdapter()
