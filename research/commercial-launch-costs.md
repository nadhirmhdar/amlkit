# Going commercial: domain, hosting and the rest of the bill

What it actually costs to turn this deployment into something a UAE DNFBP
would pay for. Prices checked September 2026; AED at the pegged 3.6725.

Everything here is about *running the thing*. `pricing-teardown.md` covers what
to charge; this covers what it costs before anyone pays you.

---

## The short answer

| | Verdict |
|---|---|
| **Domain** | **Yes, buy one.** Not for branding — for email. Verification email cannot be authenticated from `*.run.app`, so registration is broken without a domain you control. ~$12/yr |
| **Hosting** | **Already sufficient.** Cloud Run at pilot volume sits inside the free tier. ~$12/mo buys away cold starts when you want it |
| **Custom domain hookup** | **Free.** Cloudflare or Firebase Hosting in front. Do *not* pay $18.25/mo for a load balancer you don't need |
| **Email** | **The one real new cost.** SendGrid killed its free tier; the deploy already wires SendGrid. Move to Resend's free tier or budget $19.95/mo |
| **The actual gate** | A UAE trade licence, from ~AED 1,417/yr. Every website cost in this document is a rounding error next to it |

Infrastructure to go commercial is roughly **$15–35/month**. That is not the
barrier. The licence, the data-residency answer, and the legal sign-off the
README already calls for are.

---

## 1. Domain — required, and not for the reason people assume

The instinct is that a domain is about looking credible to a compliance
officer, and that a `run.app` URL looks amateur. True, but secondary.

**The real reason is email deliverability.** The app sends registration
verification links (`amlkit/mail.py`), and no operator can sign in until they
click one — `auth.login()` gates on `email_verified_at`. Deliverability of that
one message is therefore load-bearing on the whole signup flow.

Every transactional provider (SendGrid, Resend, SES, Postmark) authenticates
mail by having you publish SPF, DKIM and DMARC records **in DNS for a domain
you control**. `amlkit-xxxx.a.run.app` is a Google-owned subdomain: you cannot
add DNS records to it. Without a domain you are sending unauthenticated mail
from a shared sender reputation, straight into spam — and the recipients here
are corporate mailboxes at regulated firms, which filter harder than most.

Secondary reasons that matter to this specific buyer:

- `*.run.app` is on the Public Suffix List, so cookies are properly isolated —
  no security problem. But a compliance officer being asked to put client PII
  and sanctions screening on `amlkit-4xk2p-uc.a.run.app` will ask why.
- The evidence pack is a document that may be handed to a supervisor. The URL
  on it is part of the impression.

### What to buy

| Option | Cost | Notes |
|---|---|---|
| `.com` | ~$10–15/yr | Primary. Buy this first |
| `.ae` | AED 120–300/yr (~$33–82) | **No trade licence required** for a direct `.ae` registration — no Emirati partner, no residency. You do need a UAE presence or a local representative |
| `.co.ae` | Same range | **Requires a valid UAE trade licence**, free-zone licence, or UAE trade mark. Skip until the licence exists |

`.ae` carries real weight with a UAE regulated buyer — it signals a local
entity rather than an offshore vendor. Registry is `.aeDA`, under TDRA.

**Recommendation:** buy the `.com` now (it is where the app and email will
live), and the `.ae` defensively at the same time. Total under $100/yr. Move
to `.co.ae` once a licence exists, if the local signal proves to matter in
sales conversations.

---

## 2. Hosting — you are already fine

Current shape: Cloud Run (1 vCPU, 1 GiB, `min-instances=0`, `max-instances=10`),
SQLite on the instance replicated to GCS by Litestream, Cloud Scheduler firing
`/system/refresh` every 20 hours, images in Artifact Registry.

### Cloud Run at pilot volume: ~$0

The monthly free tier is 2,000,000 requests, 180,000 vCPU-seconds and 360,000
GiB-seconds. A pilot of five firms doing a few thousand screenings a month does
not come close. Expect **$0**.

### Cold starts: ~$12/month to remove

`min-instances=0` means the container is torn down when idle, and the next
request pays a cold start — on this image (Python + gcloud SDK + Tesseract +
Graphviz) that is not fast. The repo has already had to fix cold-start slowness
once (commit `df9d63d`, "skip eager in-process sanctions refresh on Cloud Run").

Under request-based billing, an idle minimum instance bills CPU at
$0.0000025/vCPU-s instead of the active $0.000024 — a 10× discount:

| | Monthly |
|---|---|
| Idle CPU, 1 vCPU × 730h | $6.57 |
| Memory, 1 GiB × 730h | $6.57 |
| Less free tier | −$1.35 |
| **`min-instances=1`** | **≈ $12/month** |

That is cheap enough to be worth doing the moment a paying customer exists.
Don't do it before then.

### Costs that are easy to miss

**Artifact Registry accumulates forever.** The deploy tags images by
`${{ github.sha }}` (`.github/workflows/source-canary.yml`) and nothing ever
deletes them. This image is large — `python:3.11-slim` plus the Google Cloud
CLI, Tesseract with English *and* Arabic data, Graphviz and Litestream. At
roughly 1 GB per deploy and $0.10/GB/month beyond the free 0.5 GB, a year of
active development is a slowly growing bill for images that will never run
again.

*Fixed:* `scripts/set_artifact_cleanup_policy.sh` applies exactly that — keep
the 10 most recent, delete older than 30 days. It is a one-time script rather
than a CI step for the same reason `grant_scheduler_iam.sh` is: setting a
cleanup policy needs `artifactregistry.repositories.update`, and permanently
widening the deploy service account's grant to perform a one-time repo setting
would be the wrong trade. **Still needs running once** against the project.

**How to know nothing important gets deleted.** Google's cleanup-policy
documentation does not claim any protection for an image that is currently in
use — Artifact Registry will delete one a live Cloud Run revision depends on.
With `min-instances=0` this service scales to zero routinely, so that failure
would not show up at delete time; it would show up the next time Cloud Run
tried to start an instance and found nothing to pull.

Artifact Registry does have a `--dry-run` mode, but its results land in Cloud
Logging Data Access audit logs, need the data-write audit log type enabled
first, and take **at least a day** to appear. Good for ongoing assurance,
useless for "am I about to break production".

So the script reports before it writes anything. Run with no arguments and it
prints every version with a KEEP/DELETE verdict, marks which ones Cloud Run
revisions reference, and **refuses to proceed** if an image serving live
traffic would be caught — or if it could not determine what is serving at all,
which fails toward not deleting:

```
KEEP         0d  sha256:new00           tag0
DELETE     200d  sha256:OLDSERVING      pinned  <== SERVING: amlkit-old (100% of traffic)

REFUSING TO APPLY:
  ! image serving live traffic would be deleted: sha256:OLDSERVING
```

The dangerous case is real rather than theoretical: traffic pinned to an older
revision (a rollback, a canary that was never promoted) can leave the serving
image both outside the 10 most recent *and* older than 30 days. Nothing is
written without `--apply`, and `--apply` re-runs the whole check first.

The report is a faithful reimplementation of the policy's rules, not the
policy itself — Google evaluates the real thing server-side. It exists to
catch the dangerous case immediately, not to replace the official dry run.

**Litestream's GCS write volume.** Continuous WAL replication means frequent
Class A operations, which are billed per operation rather than per byte. The
database itself is tiny and storage is negligible; the *operations* line is the
one to look at. Check an actual bill before assuming it rounds to zero.

**Cloud Scheduler** is free — the first 3 jobs per month are included, and
there is one.

### Data residency — the question that isn't about money

**Google Cloud has no region in the UAE.** The nearest are Doha
(`me-central1`) and Dammam (`me-central2`); a Kuwait region is in build. So a
UAE-regulated firm's customer PII, screening records and audit trail are
sitting outside the UAE.

This will come up in a sales conversation with anyone who has been through a
supervisory inspection, and "it's in Qatar" is a better answer than "it's in
`us-central1`" — worth confirming which region `GCP_REGION` actually points at,
since it was set for convenience rather than for this reason.

Not a blocker, and not a cost. But it belongs in the same bucket as the
README's existing "a UAE-qualified adviser should sign off" caveat: a question
to have an answer ready for, not to discover in front of a customer.

---

## 3. Putting a domain in front of Cloud Run — three options, two of them free

| Option | Cost | Verdict |
|---|---|---|
| **Cloud Run domain mapping** | Free | **No.** Still Preview, explicitly not recommended for production, latency issues, limited regions. Also cannot disable TLS 1.0/1.1 — an awkward thing to explain to a security-conscious buyer |
| **Cloudflare (free plan)** | Free | **Yes.** Free DNS + Universal SSL on the apex and first-level subdomains, plus WAF and DDoS protection you would otherwise not have. Set SSL mode to **Full (strict)**, not Flexible — Flexible causes redirect loops against Cloud Run — and turn off "Always use HTTPS" |
| **Firebase Hosting (Spark)** | Free | **Also fine.** Free tier includes custom domain, managed SSL, and a global CDN, and it rewrites cleanly to Cloud Run. Same GCP project, one less vendor |
| **Global external Application Load Balancer** | **$18.25/mo** + data processing | **No.** $0.025/hour for the forwarding rule, before traffic. You are buying nothing you need at this scale |

Either free option is production-grade here. Cloudflare edges it for the WAF
and because DNS, mail records and the proxy end up in one place.

---

## 4. Email — the one line item that genuinely changed

**SendGrid removed its free plan in May 2025.** It is now a 60-day trial at 100
emails/day, then $19.95/month minimum.

This is live, not hypothetical: the deploy workflow already wires
`AMLKIT_SMTP_*` to SendGrid's SMTP relay (commit `60d699c`). So either a paid
plan is running, or that trial has lapsed and registration verification email
is not sending. Worth checking the account state today.

> **This turned out to be a security bug, not just a cost question.**
> `mail.send_verification_email` used to return a bool, and `False` meant both
> "no SMTP configured" (a supported dev state, where showing the link is the
> point) and "SMTP configured but the send failed". Both registration routes
> branched on `if not emailed` and handed the raw verification token back to
> whoever submitted the form. That token activates a fully-privileged MLRO
> account, and proving control of the mailbox is the entire purpose of the
> check — so a deployment whose provider had lapsed was letting anyone
> register under an address they did not own and activate it immediately.
>
> Fixed: the outcome is now three-valued (`SENT` / `NOT_CONFIGURED` /
> `FAILED`), only `NOT_CONFIGURED` may reveal the link, and every send records
> its outcome in the audit log so a failing provider is visible rather than
> inferred from nobody signing up. See `TestConfiguredMailFailureDoesNotLeakTheToken`.

| Provider | Free tier | Paid from | Notes |
|---|---|---|---|
| **Resend** | **3,000/mo**, 100/day, 1 domain | $20/mo (50k) | Comfortably covers verification email for a long time. Best fit now |
| **Amazon SES** | None for new accounts since July 2026 ($200 credits over 6 months instead) | $0.10 per 1,000 | Cheapest at volume, most setup |
| **SendGrid** | Trial only | $19.95/mo | Already wired; no reason to stay |
| **Brevo / Postmark** | Varies | — | Worth a look if deliverability becomes a problem |

**Recommendation:** move to Resend. `mail.py` speaks plain SMTP with no vendor
lock-in — that was a deliberate design choice and it pays off here as an
env-var change, not a code change. Budget $0 now, $20/mo when volume justifies.

Whichever provider: publish SPF, DKIM and DMARC on the new domain on day one.
That is the whole reason for section 1.

---

## 5. Everything else

| Item | Cost | Status |
|---|---|---|
| TLS certificate | **$0** | Free via Cloudflare, Firebase, or Google-managed. Never pay for this |
| Google Play Console | $25 one-time | Already paid — the Android app ships |
| Apple App Store | $99/yr | Only if iOS is ever on the table |
| Monitoring / logging | $0 at this scale | GCP free tier is generous; nothing extra needed |
| Backups | $0 | Litestream + the `backup-verify.yml` workflow already cover this |
| **UAE trade licence** | **AED 1,417 – 25,000/yr** | **The actual gate.** See below |
| Professional indemnity insurance | Not priced | Worth quoting before the first paying client. A tool that produces compliance evidence carries a different liability profile than ordinary software |

### The licence is the real number

You cannot invoice UAE clients without one. Options, cheapest first:

- **E-Trader licence** — AED 1,416.50/yr. Mainland, home-based, covers software
  development under the professional category. Requires UAE residence. The
  obvious starting point for a solo commercial launch.
- **Free-zone freelance permit** — AED 5,500–25,000/yr depending on zone.
- **E-commerce licence** — from AED 5,525 (0-visa free zone) to ~AED 40,000
  (mainland with office).

At AED 1,417, the E-Trader licence is **more than the entire annual
infrastructure and domain bill combined**. Which is the useful thing to know:
the technical cost of going commercial is essentially noise, and the decision
is a business and regulatory one, not an infrastructure one.

---

## What to do, in order

Done in code (nothing to action):

- ~~Make a failing mail provider visible instead of silent~~ — and closed the
  token-leak it was causing. See section 4.
- ~~Add an Artifact Registry cleanup policy~~ — written as
  `scripts/set_artifact_cleanup_policy.sh`; still needs **running once**.
- ~~Smoke-test the adverse-media provider~~ — GDELT is now in the daily source
  canary, non-blocking, watching for schema drift.

Yours, in order:

1. **Check whether SendGrid is still sending.** If that trial lapsed,
   registration has been failing. The audit log now records the delivery
   outcome of every send, so `SELECT detail FROM audit_log WHERE
   action='operator.verification_sent'` answers this directly.
2. **Run `scripts/set_artifact_cleanup_policy.sh`.** Needs `GCP_REGION` set
   and a gcloud session with repo-admin rights. Stops a slow leak.
3. **Buy the `.com`.** ~$12. Everything else depends on it.
4. **Move email to Resend**, publish SPF/DKIM/DMARC on the new domain. Free.
5. **Put Cloudflare in front**, point the domain at Cloud Run, set
   `AMLKIT_APP_BASE_URL` to it so verification links stop pointing at
   `run.app`. Free.
6. **Buy the `.ae`** defensively. ~AED 200.
7. *Then* the business questions: licence, data-residency answer, insurance,
   and the UAE-qualified sign-off the README already flags.

Steps 1–6 cost about $12 and an afternoon. Step 7 is the actual project.

---

## Sources

- GDELT/GCP and vendor pricing checked September 2026 against:
  Cloud Run pricing, Cloud Load Balancing pricing, Firebase pricing,
  Cloudflare free plan, Cloud Run custom-domain mapping docs,
  Resend / SendGrid / Amazon SES published pricing, `.aeDA` registrar pricing,
  and UAE licensing guidance (E-Trader, free-zone freelance permit,
  e-commerce licence).
- Prices move. Re-check before committing budget, especially the email tier —
  that is the one that changed most recently and most disruptively.
