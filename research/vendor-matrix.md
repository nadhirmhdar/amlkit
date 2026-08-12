# Vendor & Data-Source Matrix

Research captured August 2026. Pricing is as published by vendors or by third-party comparison; enterprise vendors do not publish and are shown as reported ranges.

---

## 1. Published-pricing vendors (the real competitive floor)

These matter most: they are the only ones a UAE DNFBP can actually buy without a sales call, so they define what our tool must beat.

| Vendor | Model | 100 entities/yr | 1,000 entities/yr | Monitoring | IDV | Notes |
|---|---|---|---|---|---|---|
| **KYC2020** | Per-scan or annual per-entity | **$152** | **$1,040** | Bundled | +$105/100 | Cheapest credible option found |
| **NameScan** | Pay-per-scan, annual packs | $240 | $1,600 | **Not offered** | $2.00/entity | No ongoing monitoring is a compliance gap |
| **Sumsub** | Monthly per entity | n/a at self-serve | ~$2.27/entity | **+$0.08/scan extra** | Bundled | Monitoring surcharge is buried in technical docs |
| **ComplyAdvantage** | Monthly per monitored entity | $99/mo floor | $4.43/entity | Bundled | Not offered | Strong data reputation; needs 3rd-party IDV (+$1.05–1.50) |
| **AML Watcher** | Annual per entity | $375/mo floor | $7.30/entity | Bundled | Not offered | Highest per-entity of the transparent set |

**Read:** a UAE broker with 500 clients pays roughly **$500–$3,650/yr** at the transparent end. Entry *floors* ($99–$375/mo) hurt small DNFBPs most — a 40-client firm pays the same minimum as a 400-client one. That floor, not the unit price, is the real barrier.

## 2. Enterprise tier (price ceiling — not our competition, but sets the anchor)

| Vendor | Positioning | Reported cost |
|---|---|---|
| LSEG **World-Check** | Premium curated PEP/sanctions data | Enterprise licensing, unpublished |
| **Dow Jones** Risk & Compliance | Curated risk data + adverse media | $10k–$100k+/yr; mid-market $25k–75k; enterprise $200k+ |
| **LexisNexis** Risk | Bridger/RiskNarrative screening | Unpublished |
| **Moody's** (GRID/Orbis) | Entity + ownership data | Unpublished |
| Napier AI / NICE Actimize / Oracle FCCM / Fenergo / Quantexa | Enterprise AML platforms & TM | Unpublished, six figures typical |

None publish pricing. All require a sales conversation to get a number — itself a cost driver (see teardown §4).

## 3. UAE-native / UAE-focused

| Vendor | Base | Offer | Pricing |
|---|---|---|---|
| **azakaw** | UAE (DIFC) | eKYC/KYB, onboarding, TM, screening, corporate compliance | Not published |
| **binderr** | UAE | Compliance tooling for accountants & corporate service providers | Not published |
| **Focal** (getfocal.ai) | MENA | AML/TM for MENA banks & fintechs | Not published |
| **ZIGRAM** | India/UAE | AML data + screening | Not published |
| **Sanction Scanner** | TR, strong UAE presence | Screening + TM, free single-name lookup tool | Not published |
| **AML UAE** (amluae.com) | UAE | Consultancy, not software — best plain-English regulatory explainers found | Services |

**Observation:** not one UAE-focused vendor publishes pricing. For a segment dominated by small firms, that opacity is itself a market failure — and an opening.

---

## 4. Data sources — what v1 runs on

| Source | Format | Key | Cost | Role |
|---|---|---|---|---|
| **OpenSanctions** (`ae_local_terrorists`) | FtM JSON, CSV, XLS | none | Free non-commercial | UAE Local Terrorist List — **770 entities** (190 persons, 144 orgs, 10 addresses, 1 vessel), refreshed **daily** |
| OpenSanctions default | FtM JSON | none | Free non-commercial | Consolidated global sanctions + PEP |
| **UAE EOCN** (uaeiec.gov.ae) | PDF + Excel | none | Free | Authoritative local list + email alert subscription |
| **UN Security Council Consolidated** | XML, PDF, HTML | none | Free | Mandatory under UAE law |
| **OFAC** SDN + Consolidated | XML, CSV | none | Free | US sanctions |
| **UK OFSI** Consolidated | CSV, XML | none | Free | UK sanctions |
| **EU** Financial Sanctions Files | XML | registration token | Free | EU sanctions |
| **GLEIF** LEI | API/bulk | none | Free | Entity verification (LEI weighted 0.95 in OpenSanctions matcher) |
| **GDELT** | API | none | Free | Adverse media |
| **Wikidata** | SPARQL | none | Free | PEP enrichment |
| World Bank Debarred | CSV | none | Free | Procurement debarment |
| Companies House UK | REST | free key | Free | Corporate/UBO |

## 5. Engine options evaluated

**yente** (OpenSanctions' own engine) — MIT licensed, free to run. Requires **Elasticsearch/OpenSearch, 8GB RAM minimum, 16GB recommended**, 60GB storage, two Docker containers. Auto-refreshes bulk data hourly.

**Decision: build our own matcher on Postgres rather than deploy yente.** Reasoning:
- The UAE mandatory core is small — 770 local entities plus the UN list. Elasticsearch at 16GB is disproportionate infrastructure for a tool meant to run on a compliance officer's machine.
- yente's matching is a black box to us at the point where we most need control: **Arabic name handling**, our chosen differentiator.
- Postgres `pg_trgm` + phonetic keys gives adequate candidate generation at this scale, with our scoring layer on top and full visibility into every score.
- yente stays available as a documented alternative backend if volumes ever justify it.

## 6. What we copy from OpenSanctions' matcher (logic-v2)

Their published feature weights are a well-tested starting point and we adopt them rather than inventing our own:

| Feature | Weight |
|---|---|
| Name match | 1.00 |
| Address entity match | 0.98 |
| Crypto wallet match | 0.98 |
| LEI / SWIFT BIC | 0.95 |
| Tax IDs (INN, OGRN) | 0.95 |
| Country **mismatch** | −0.20 |
| DOB day mismatch | −0.25 |
| DOB year mismatch | −0.15 |
| Gender mismatch | −0.20 |

Also adopted: a **family-name weight multiplier (~1.3×)** for person matching, and a tunable fuzzy cutoff factor.

**Where we go beyond them:** logic-v2 uses generic cross-script reference data. We add a UAE-specific Arabic layer — transliteration variant classes, patronymic-particle tokenisation, and name-chain permutation — which is the failure mode that generates the most false negatives *and* false positives in this market.

---

## 7. Hard requirements extracted from regulators

These come from EOCN and MOET and are **system requirements, not preferences**:

1. Screening must run **on list update, immediately — implemented within 24 hours**.
2. Screening must also run: before onboarding, at periodic KYC review, on material customer change, and **before processing any transaction**.
3. Screening covers customers, potential clients, transaction parties, **beneficial owners**, and directly/indirectly related persons.
4. On match: freeze **without delay and without prior notice to the listed person**.
5. Report matches immediately — MOET channel `AML@economy.ae` / 8001222; suspicions via goAML.
6. Lists in scope: UNSC Consolidated, UAE Local Terrorist List, **counter-proliferation lists** (now standalone under Law 10/2025).

Requirement 1 drives the architecture: the daily-refresh CI job is not housekeeping, it is the compliance control. Requirement 3 means screening cannot stop at the named customer — the UBO graph must be screened too, which several cheap tools do not do.
