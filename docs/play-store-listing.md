# Play Store listing copy

Draft copy for the Store presence fields in Play Console (see
`docs/google-play-steps.md` §5). Edit before pasting — in particular, the
full description below is written for a firm that has already deployed its
own amlkit server; adjust if that's not yet true when you publish.

## App name (≤30 characters)

```
amlkit
```

## Short description (≤80 characters)

```
Sanctions/PEP screening and AML case management for UAE DNFBPs.
```
(65 characters)

## Full description (≤4000 characters)

```
amlkit is sanctions and PEP screening plus customer due diligence for UAE
DNFBPs — real estate brokers, precious-metals dealers, corporate service
providers, auditors, and law firms carrying AML obligations under Federal
Decree-Law No. 10 of 2025 and Cabinet Resolution No. 134 of 2025.

This app connects to your firm's own amlkit deployment — it does not screen
against a shared, multi-tenant cloud. Your customer data stays on the server
your firm controls.

WHAT YOU CAN DO FROM YOUR PHONE

• Screen a name against sanctions and PEP lists in seconds, with
  Arabic-script matching that handles transliteration, patronymic
  particles, and reordered name chains
• Onboard a customer and screen every beneficial owner at the 25%
  threshold, with the senior-official fallback the regulation requires
• Triage the alert queue: confirm, dismiss with a reason code, or escalate
  — with independent second-review enforced on dismissing a sanctions or
  proliferation-financing match
• Review a customer's full case file: risk rating, screening history,
  transactions, case notes, and recorded signatures
• Manage operators, the org-wide alert threshold, and trigger a sanctions
  list refresh (MLRO role)
• Draft, submit, and export STR/SAR reports in goAML XML format
• Review the full audit trail for your organization

WHY IT'S DIFFERENT

Most affordable screening tools treat Arabic names as a generic
transliteration problem. amlkit handles it linguistically — orthographic
normalization, positional semivowels, theophoric compound rejoining, and
order-independent canonical keys — because in the UAE, Arabic name matching
isn't an edge case, it's the main case.

Every alert stores its full scoring evidence, because "the algorithm said
so" isn't an answer an examiner accepts.

REQUIREMENTS

You need an account with a firm already using amlkit — this app is not a
public sanctions lookup tool, and there is no self-service sign-up outside
of your firm's own deployment. See your firm's MLRO to get access.

Camera permission is optional, used only to speed up onboarding by scanning
a passport's machine-readable zone; every field it fills in can also be
typed by hand.
```
(1,466 characters)

## Category

Business

## Contact details

Required by Play Console — a real support email and (recommended) a website.

## Privacy policy URL

Publish the drafted policy first — see the artifact from this session, or
`docs/google-play-steps.md` §5.
