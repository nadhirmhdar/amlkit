---
name: amlkit-full-review
description: Comprehensive review of the amlkit UAE AML/CFT codebase using 13 specialist reference repositories. Covers security audit, QA, TDD gap-fill, UX audit, live webapp testing, autonomous agent bug-hunt, scraping robustness, RAG/NLP benchmarking, MCP integration, public API survey, AI automation patterns, workflow pipeline validation, and infrastructure audit.
---

# amlkit Full Review

Run this skill at the start of any session in which you want a thorough, multi-angle review of the amlkit codebase. It maps each of the 13 reference repositories to a specific area of the app and gives you a step-by-step workflow to execute.

## Reference Repositories

All repos are cloned (shallow) under `/home/user/`. Re-clone with `git clone --depth 1 <url>` if the session is fresh.

| Path | Repo | Strength |
|------|------|----------|
| `/home/user/gstack` | nadhirmhdar/gstack | 23+ specialist slash commands — `/cso` (security), `/qa`, `/review`, `/ship`. Encodes a "software factory" methodology. |
| `/home/user/superpowers-clone` | nadhirmhdar/superpowers-clone | TDD + spec-driven development methodology for coding agents. 14 skills for writing tests before code. |
| `/home/user/ui-ux-skills-clone` | nadhirmhdar/UI-UX-skills-clone | 161 reasoning rules + 67 UI styles for design systems. `uipro` design-system skill. |
| `/home/user/awesome-claude-skills-cloned` | nadhirmhdar/awesome-claude-skills-cloned | 1000+ Claude skills incl. `webapp-testing/` (browser-driven live URL checks) and `composio-skills` (1000+ app integrations). |
| `/home/user/anthropics-skills` | nadhirmhdar/anthropics-skills | Official Anthropic reference skill library — canonical SKILL.md format and best-practice patterns. |
| `/home/user/ai-engg-clone` | nadhirmhdar/ai-engg-clone | 93+ production AI engineering templates — ColBERT RAG, corrective-RAG, multilingual NLP, fine-tuning. |
| `/home/user/awsm-llm-apps-cloned` | nadhirmhdar/awsm-llm-apps-cloned | 100+ multi-agent, RAG, and voice app templates (Apache-2.0). Always-on-agent and vertical-use-case patterns. |
| `/home/user/openhands-cloned` | nadhirmhdar/openhands-cloned | OpenHands autonomous AI coding agent (SWE-bench rated, formerly OpenDevin). Browses, runs tests, iteratively fixes. |
| `/home/user/scrapling-cloned` | nadhirmhdar/scrapling-cloned | Adaptive web scraping — bot-detection evasion, signature-based element tracking, JS-rendered pages. |
| `/home/user/langflow-cloned` | nadhirmhdar/langflow-cloned | Visual drag-and-drop LLM pipeline builder; deploys flows as REST/MCP endpoints. |
| `/home/user/mcp-servers-cloned` | nadhirmhdar/mcp-servers-cloned | Curated awesome-list of MCP server implementations — canonical reference for integrations. |
| `/home/user/public-APIS-cloned` | nadhirmhdar/public-APIS-cloned | 1600+ free public APIs across 40+ domains — sanctions, financial crime, PEP, adverse media. |
| `/home/user/freefordev-cloned` | nadhirmhdar/freefordev-cloned | 1600+ permanently-free infrastructure/SaaS services — CI/CD, monitoring, auth, storage, observability. |

## Review Workflow

Execute the steps below in order. Each step names the tool/skill to invoke and the amlkit files it targets.

---

### Step 1 — Security Audit (CRITICAL)
**Tool:** gstack `/cso` and `/review` slash commands  
**Target files:** `amlkit/api/app.py`, `amlkit/auth.py`, `amlkit/api/mobile.py`, `amlkit/db.py`  
**What to check:**
- SQL injection surface (all raw `f""` queries, parameterised vs. not)
- CSRF enforcement on every POST route — verify cookie + hidden-field synchronizer token is validated
- Session fixation, cookie flags (`HttpOnly`, `Secure`, `SameSite`)
- Bearer-token routes in `mobile.py` — timing-safe comparison, expiry
- Password hashing (argon2) — verify parameters meet OWASP 2024 recommendations
- `ADMIN_API_SECRET` and `SCHEDULER_SECRET` env-var hardening

```
# In the gstack-enabled session:
/cso  # paste amlkit/api/app.py content
/review amlkit/auth.py
```

---

### Step 2 — QA Pass (CRITICAL)
**Tool:** gstack `/qa` and `/review`  
**Target files:** `tests/`, `amlkit/api/app.py`, `amlkit/match/engine.py`  
**What to check:**
- Edge cases not covered by pytest suite (error paths, concurrent DB writes, lock-retry decorator)
- Tenant isolation — confirm no query runs without `org_id`
- Screening engine false-positive/negative boundary conditions
- goAML export XML schema compliance (STR, SAR, all 9 report types)

---

### Step 3 — TDD Gap-Fill (HIGH)
**Tool:** superpowers-clone TDD skill  
**Target:** All backlog features in Product Dev board items p14–p22  
**Workflow:**
1. For each unbuilt feature, write the failing test first (spec-driven)
2. Use the superpowers `tdd` skill to generate test stubs
3. Confirm tests are wired to the existing `_register()` helper in `tests/test_api.py`

```
# Load the TDD skill from superpowers-clone:
Skill: /home/user/superpowers-clone/.claude/skills/tdd/SKILL.md
```

---

### Step 4 — UX Audit (HIGH)
**Tool:** ui-ux-skills-clone `uipro` skill (161 reasoning rules)  
**Target:** `amlkit/web/templates/`  
**What to audit:**
- Nationality dropdown on all customer forms — full 195-country ISO list + integrated search (p32)
- Freeze Obligations (`/freeze-obligations`) — move inside Dashboard as collapsible section (p31)
- Alerts (`/alerts`) — move to left-side expandable drawer inside Dashboard (p33)
- Top nav restructure — profile avatar chip top-right with dropdown: Profile, Admin, Audit Trails, Policies (p34)
- Form usability: label placement, error states, required-field indicators

---

### Step 5 — Live Webapp Testing (HIGH)
**Tool:** awesome-claude-skills-cloned `webapp-testing/` skill  
**Target URL:** `https://amlkit-720622408077.me-central1.run.app`  
**Run against:**
- Customer onboarding flow (CDD form, nationality dropdown, document upload)
- Sanctions screening result page
- Dashboard (freeze obligations, alerts)
- STR filing flow
- Mobile API endpoints via bearer token

```
# Load the skill:
Skill: /home/user/awesome-claude-skills-cloned/webapp-testing/SKILL.md
```

---

### Step 6 — Autonomous Bug Hunt (HIGH)
**Tool:** OpenHands autonomous agent  
**Target:** Full amlkit codebase  
**Instructions for OpenHands:**
1. Clone the repo, run `pytest tests/ -x -q`
2. For each failure: identify root cause, apply minimal fix, re-run
3. Auto-generate stub tests for functions with no coverage (focus: `ingest/`, `match/`, `reporting/goaml.py`)
4. Report all findings with file:line references

---

### Step 7 — Scraping Robustness (MEDIUM)
**Tool:** scrapling-cloned adaptive tracker  
**Target:** `amlkit/screening/adverse_media.py` (GDELT-based)  
**What to check:**
- Replace fragile CSS selectors with scrapling's signature-based element tracking
- Add bot-detection evasion headers (GDELT does not block, but test for JS-rendered fallback)
- Validate that scraper returns structured results for a known entity (e.g. "Al Qaeda")

---

### Step 8 — RAG / Name-Matching Benchmark (MEDIUM)
**Tool:** ai-engg-clone RAG templates (ColBERT, corrective-RAG, multilingual)  
**Target:** `amlkit/match/engine.py`, `amlkit/match/scorer.py`, `amlkit/names/arabic.py`  
**What to check:**
- Compare current Jaro-Winkler / Levenshtein scorer against ColBERT-based embedding similarity
- Test Arabic name canonicalization (453-line `arabic.py`) against multilingual NLP templates
- Evaluate whether corrective-RAG reranking would improve PEP/sanctions match precision

---

### Step 9 — MCP Integration Survey (MEDIUM)
**Tool:** mcp-servers-cloned (curated awesome-list)  
**Target:** New integrations for amlkit  
**What to identify:**
- Sanctions database MCP servers (OFAC, UN, EU, UK)
- File system MCP server (replace custom `storage.py` abstraction)
- PostgreSQL MCP server (migration path from SQLite)
- Identify any AML/financial-crime-specific MCP servers in the list

---

### Step 10 — Public API Survey (MEDIUM)
**Tool:** public-APIS-cloned directory  
**Target:** `amlkit/ingest/`, `amlkit/screening/`  
**What to find:**
- Free sanctions / PEP list APIs (supplement OFAC, UN, EU, UK scrapers)
- Adverse media APIs (supplement GDELT-based scraper)
- Company registry APIs (UAE + international) for CDD
- Beneficial ownership APIs

---

### Step 11 — AI Automation Patterns (MEDIUM)
**Tool:** awsm-llm-apps-cloned templates  
**Target:** New amlkit automation features  
**Survey for:**
- Always-on agent patterns → automate CDD refresh and sanctions re-screening
- STR drafting assistant (LLM-assisted goAML XML generation)
- Alert triage agent (route alerts to responsible officer automatically)

---

### Step 12 — Workflow Pipeline Validation (MEDIUM)
**Tool:** langflow-cloned  
**What to model:**
- Build amlkit's core workflow as a Langflow visual pipeline:
  `Customer onboarding → Sanctions screening → Alert triage → Four-eyes review → STR filing → goAML export`
- Deploy as a REST endpoint and compare state transitions to the actual route logic in `api/app.py`
- Identify any gaps or unreachable states

---

### Step 13 — Infrastructure Audit (LOW)
**Tool:** freefordev-cloned service directory  
**Target:** amlkit CI/CD and monitoring stack  
**What to audit:**
- CI/CD: confirm GitHub Actions pipeline covers lint + pytest; identify free-tier upgrade options
- Monitoring: APScheduler has no failure alerting — survey freefordev for free observability (Grafana Cloud, Better Uptime, Sentry free tier)
- Secrets management: validate env-var handling; check for free-tier Vault/Doppler options
- Backup: SQLite WAL mode — confirm backup strategy exists; survey free-tier backup services

---

## Quick-Start Command

To run the full review in one session:

```
/amlkit-full-review
```

The skill will load this file and you can work through Steps 1–13 sequentially or jump to the area most relevant to the current sprint.

## Boards Reference

All tasks from this review are tracked on the amlkit Boards artifact:
- **Tests board** (t1–t33): items t1–t20 are existing test tasks; t21–t33 are the repo-linked tasks above
- **Product Dev board** (p1–p34): UX and feature work referenced in Steps 3–4
- Artifact URL: https://claude.ai/artifact/G8gcUmVTDGZadVhXSUHbxL
