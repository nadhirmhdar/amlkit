# HELD proposal (lead, 2026-11-22, master c42c77c): evidence-PDF disclaimer overlay, delisting deletes confirmed decisions, CR-49 × PC1 interaction

Status: **HELD for human review.** Each fix edits an existing template, stylesheet, schema or loader, which the
routine may not change. Repros (scratch SQLite, no network) exit 0 while the defect reproduces:
`repro_lead/ev1_evidence_pdf_disclaimer_overlay_2026_11_22.py`, `repro_lead/dl1b_delist_true_positive_2026_11_22.py`.

## 1. EV1: the first-login "Important Notice" dialog is printed into the evidence PDF

Mechanism (master `c42c77c`):
- `web/templates/evidence.html:1` extends `base.html`; `api/routers/customers.py:512` passes `session` into the
  PDF render context.
- `web/templates/base.html:279-290` renders `<dialog id="disclaimer-modal" class="feedback-modal" ... open>` when
  `session and not session.disclaimer_acknowledged`.
- `web/static/app.css:1042-1048` makes an open `.feedback-modal` a full-viewport fixed layer with a dimmed
  background; the `@media print` block (`app.css:1258-1266`) hides `button`/`.btn` (so the "I Understand"
  button disappears) but not the dialog.

Lead repro output:
```
EV1  operator disclaimer_acknowledged_at before export: None
EV1  unacknowledged PDF page 1 contains 'Important Notice': True
EV1  POST /acknowledge-disclaimer -> 303
EV1  acknowledged PDF page 1 contains 'Important Notice': False
EV1 reproduces (scoped to unacknowledged session)
```

Scope: only operators who have not yet clicked "I Understand" (acknowledgement is per operator). In a browser
`web/static/js/app.js:639-645` opens the dialog with `showModal()` and cancels Escape, so the page behind is inert
and a JS-enabled user cannot click the PDF link before acknowledging; the PDF is reached unacknowledged only by
a typed/bookmarked URL, no-JS browsing, or a script (as the mlro-user driver did). Browser Ctrl+P of the HTML evidence page has the
same print CSS. Lead severity: **LOW** (cosmetic on a regulator-facing document, rare path, trivial fix).

Proposed diff (either line alone fixes the PDF; both is cleanest):
```diff
--- a/amlkit/web/static/app.css
+++ b/amlkit/web/static/app.css
 @media print {
   body { background: #fff; color: #000; }
-  .sidebar, .nav-hamburger, .mobile-tabbar, .no-print, button, .btn { display: none !important; }
+  .sidebar, .nav-hamburger, .mobile-tabbar, .no-print, button, .btn,
+  .feedback-modal { display: none !important; }
```
```diff
--- a/amlkit/web/templates/base.html
+++ b/amlkit/web/templates/base.html
-    <dialog id="disclaimer-modal" class="feedback-modal" aria-labelledby="disclaimer-modal-title" open>
+    <dialog id="disclaimer-modal" class="feedback-modal no-print" aria-labelledby="disclaimer-modal-title" open>
```
New test (in `tests/test_evidence_pdf.py`, needs WeasyPrint): register, onboard, do **not** acknowledge, fetch
`/customers/{id}/evidence.pdf`, assert `"Important Notice"` is not in page 1 text (pypdfium2 is already a
dependency). The skeptic's broader point stands: one test per printable view with an unacknowledged session.

## 2. DL1b: delisting cascade-deletes a confirmed UN true-positive alert and its four-eyes history; the freeze survives orphaned

Owed from the 11-21 lead report. Lead repro output (UN dataset `un_sc_sanctions`, exact name, onboarded,
disposed `true_positive` / `confirmed_match`, then a refresh drops the entity):
```
DL1b  before delisting: alert 1 status=true_positive; alert_reviews=1; freeze_obligations=[(1, 1, 'pending_execution')]
DL1b  after delisting: alert row left=0; alert_reviews left=0; freeze_obligations=[(1, None, 'pending_execution', 'sanctions')]; alert.* audit rows=1
DL1b  true_positive alert cascade-deleted=True; freeze row kept but alert_id NULL=True
```

Cause: `ingest/loader.py:158-168` `DELETE FROM entities` for delisted source ids; `db.py:366`
`alerts.entity_id ... ON DELETE CASCADE`; `db.py:428` `alert_reviews.alert_id ... ON DELETE CASCADE`;
`db.py:759` `freeze_obligations.alert_id ... ON DELETE SET NULL` (also `reports.alert_id`, `db.py:740`).

Effect: the confirmed match decision (score, score_detail, narrative, proposer/confirmer rows) disappears from the
case file; only the `alert.*` audit row remains. The freeze obligation stays `pending_execution` with no link to
the match that created it, and no `resolution_reason='delisted'` is recorded, although delisting is the event that
should drive that resolution. The loader comment ("an acceptable edge case ... should have dispositioned it
before delisting") assumes disposition protects the record; for `true_positive` it does not. Lead severity:
**MEDIUM** (record-keeping of a confirmed TFS match; raised from LOW for the false-positive case).

Options (Nadhir's decision):
- (A, recommended) soft-delist: additive `entities.delisted_at TEXT` column; loader sets it instead of
  `DELETE`; candidate lookup and `entity_tokens` exclude `delisted_at IS NOT NULL`; case files show
  "delisted on <date>". Then, for a pending freeze whose entity is delisted, notify the MLRO (do not auto-resolve:
  unfreezing needs the MLRO's record of the delisting notice).
- (B) archive before delete: copy affected `alerts` + `alert_reviews` rows into new `alerts_archive` /
  `alert_reviews_archive` tables inside the same transaction, then delete as today.
- Either way, add a test: UN true_positive + freeze, delist, assert the alert (or its archive) and the freeze link
  survive.

Sketch for (A), loader:
```diff
-        if removed_ids:
-            conn.executemany(
-                "DELETE FROM entities WHERE id=?",
-                [(eid,) for eid in removed_ids],
-            )
+        if removed_ids:
+            conn.executemany(
+                "UPDATE entities SET delisted_at=? WHERE id=? AND delisted_at IS NULL",
+                [(now, eid) for eid in removed_ids],
+            )
+            conn.executemany("DELETE FROM entity_tokens WHERE entity_id=?", [(e,) for e in removed_ids])
```
(plus a re-listing path that clears `delisted_at` when the source id returns, and the matching filter in
`match/engine.py` candidate SQL; not drafted line-by-line here because it touches the hot screening query).

## 3. CR-49 multi-DOB × PC1 DOB-corroboration rule (owed analysis)

The 11-20 proposal §2 stores every listed DOB (`entities.birth_dates`) and scores against the best one; §3 adds
`_dobs_contradict(a, b)` to the PEP fold. If `_dobs_contradict` keeps comparing only the single `birth_date`,
an entity whose alternate DOB matches the other entity's DOB is kept as a separate hit: an extra alert (noise),
never a miss. The unsafe combination would be a fold that treats "any DOB present on one side" as corroboration
while ignoring a contradicting set on the other side. Rule to use when both land:

- `_dobs_contradict(A, B)` is True only when **both** sides have at least one date **and no pair** (a in A,
  b in B) agrees at the precision both carry (same year when either is year-only, else same full date).
- Fold corroboration (11-21 §1(a)) requires a positive agreement: at least one agreeing DOB pair, or an agreeing
  country with neither side's DOB set contradicting.

With that definition the two changes are independent: CR-49 only widens what counts as "agrees", and §1(b)
per-member coverage still catches any member folded in error. No conflict; land CR-49 first or together.
