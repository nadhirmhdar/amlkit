# Why AML Software Costs What It Does

Analysis from vendor research, August 2026. Purpose: locate where the cost actually sits, so the build attacks the right thing.

---

## The headline numbers

| Tier | Annual cost | Who buys it |
|---|---|---|
| Transparent self-serve | $152 – $3,650 | Small firms, 100–1,000 clients |
| Entry floors | $99 – $375 **per month regardless of volume** | Anyone, including a 40-client broker |
| Mid-market | $25,000 – $75,000 | Regulated FIs, larger DNFBPs |
| Enterprise | $200,000+ | Banks, exchanges, multinationals |

The spread between the top and bottom of this table is roughly **1,300×**. That is not explained by software.

---

## The eight cost drivers

### 1. Data licensing dominates COGS — not engineering
PEP and adverse-media databases are curated by human analyst teams tracking millions of officials, their relatives and close associates, across languages and jurisdictions. Vendors pay per-record or per-seat royalties to World-Check, Dow Jones or LexisNexis and pass them through. **The software is commodity; the data is the moat.** OpenSanctions makes this explicit and unusually honest: the engine (yente) is MIT-licensed and free, while the *data* requires a commercial licence.

### 2. Curation never finishes
Sanctions lists are public and free. Consolidated **PEP/RCA and adverse-media corpora are proprietary**, and they are re-verified continuously — a politician leaves office, a relative is added, a news article is assessed for relevance. This is a permanent salaried cost with no economies of scale in the underlying research.

### 3. Assurance and liability transfer
SOC 2, ISO 27001, model validation, regulator-facing audit trails, indemnities. Customers are not buying matching — they are buying **defensibility at examination**. That assurance apparatus is expensive to maintain and is priced in.

### 4. Enterprise go-to-market economics
Not one enterprise vendor publishes a price, and **not one UAE-focused vendor does either**. Unpublished pricing implies 6–18 month sales cycles, solution engineers, RFP teams and bespoke negotiation. Customer acquisition cost gets amortised straight into the licence — the buyer pays for the sales process that sold to them.

### 5. Consumption pricing compounds
Ongoing monitoring re-screens the **entire customer book** every time a list changes. Cost therefore scales with book size rather than with value delivered. Sumsub's `~$0.08/scan` monitoring surcharge — documented in technical pages while the main pricing page implies inclusion — is the clearest example of how this compounds quietly.

### 6. Willingness to pay is anchored to penalties, not cost-to-serve
UAE fines run **AED 10,000 to AED 5,000,000 per violation**, plus licence and reputational risk. Against that exposure a $75,000 tool reads as cheap. This is textbook value-based pricing, and it means prices are set by fear, not by cost.

### 7. Switching costs entrench renewals
Once a tool is embedded in onboarding and has been accepted by an auditor, replacing it is itself a regulatory project requiring re-validation. Renewal pricing power follows.

### 8. The false-positive tax is self-reinforcing
Weak matching generates alert volume. Vendors then upsell tuning, AI triage and analyst tooling to fix a problem their own matching created. The customer pays twice: once for the noisy engine, once for the noise suppression — and a third time in analyst salaries.

---

## Where the money is *not*

Stripping the above away, the **mandatory core of UAE compliance costs nothing in data licensing**:

- UAE Local Terrorist List — free from EOCN, 770 entities
- UN Security Council Consolidated — free, mandatory
- Counter-proliferation lists — free
- OFAC / EU / UK — free, all public domain

These are precisely the lists UAE law *requires* screening against. **The legally mandatory portion of a UAE AML programme carries zero data cost.** What costs money is curated global PEP and adverse-media coverage — genuinely valuable to a global bank, substantially less so to a Dubai real-estate broker screening mostly local and GCC counterparties.

## The three openings

**1. The entry floor is the real barrier, not the unit price.**
A 40-client corporate service provider pays the same $99–$375/month minimum as a 400-client one. Per-entity economics are irrelevant to them; the floor is what excludes them. A tool with no floor serves a segment the market currently prices out — while still being **legally obligated to comply**.

**2. Arabic name matching is the weakest link across the entire market.**
Every major platform treats Arabic as a transliteration problem solved by generic cross-script reference data. In the UAE it is the *primary* matching problem: Mohammed/Muhammad/Mohd variants, `bin`/`ibn`/`bint`/`al-` particles, and 3–5 element name chains that arrive in inconsistent order. This generates both false negatives (missed sanctions hits — a regulatory failure) and false positives (alert fatigue — an operational cost). Getting it right is a genuine technical win, not just a cheaper price.

**3. Cheap tools quietly omit mandatory features.**
NameScan offers **no ongoing monitoring at all** — yet EOCN requires screening on every list update, implemented within 24 hours. ComplyAdvantage and AML Watcher offer no IDV. Several tools screen the named customer but not the **beneficial owners**, which MOET explicitly requires. A tool that is cheap *and* actually covers the mandatory surface is not currently on the market for small UAE firms.

---

## What this means for the build

- Ship the **free mandatory core** first — UN, UAE Local Terrorist List, PF lists, OFAC/EU/UK. This is complete regulatory coverage at zero data cost.
- Treat curated global PEP/adverse-media as an **optional paid upgrade**, not a dependency. Free proxies (OpenSanctions PEP data, Wikidata, GDELT) cover a meaningful share of realistic UAE risk.
- **Have no entry floor.** The cost structure of self-hosted free data means marginal cost per customer is near zero; a floor would be pure margin and would re-create the exact barrier we are attacking.
- Invest engineering effort disproportionately in **matching quality**, because that is where incumbents are weak, where the regulator's risk actually sits, and where cost driver #8 can be defeated rather than monetised.
- Screen the **UBO graph**, not just the named party — mandatory, and commonly skipped at the cheap end.
