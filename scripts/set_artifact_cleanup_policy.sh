#!/bin/bash
# Prune Artifact Registry, but prove nothing load-bearing goes first.
#
# The deploy tags every image by ${{ github.sha }} (see .github/workflows/
# source-canary.yml) and nothing has ever deleted one. The image is large --
# python:3.11-slim plus the Google Cloud CLI, Tesseract with English AND
# Arabic language data, Graphviz and Litestream -- so at roughly 1 GB a deploy
# this grows forever, at $0.10/GB/month beyond the free 0.5 GB, for images
# that will never run again.
#
# ---------------------------------------------------------------------------
# WHY THIS SCRIPT REPORTS BEFORE IT DELETES
# ---------------------------------------------------------------------------
# Google's cleanup-policy documentation does not claim any protection for an
# image that is currently in use. Artifact Registry will delete an image a
# live Cloud Run revision depends on, and with min-instances=0 this service
# scales to zero routinely -- so the failure would not appear at delete time.
# It would appear the next time Cloud Run tried to start an instance and
# found nothing to pull. A quiet Sunday, then a dead service on Monday.
#
# Artifact Registry does offer a --dry-run mode, but its results land in Cloud
# Logging Data Access audit logs, need the data-write audit log type switched
# on first, and take at least a day to appear. That is the right belt for
# ongoing assurance and the wrong tool for "am I about to break production".
#
# So this script computes the answer locally and immediately: it lists every
# version, applies the same keep/delete rules the policy will apply, and then
# refuses to continue if any image a traffic-serving Cloud Run revision needs
# would be caught. Nothing is written without --apply, and --apply re-runs the
# whole check first.
#
# Honest limit: the report is a faithful reimplementation of the policy's
# rules, not the policy itself -- Google evaluates the real thing server-side.
# It is here to catch the dangerous case before it happens, not to replace the
# official dry run. Run both if you want belt and braces.
#
# ---------------------------------------------------------------------------
# USAGE
#   GCP_REGION=<region> scripts/set_artifact_cleanup_policy.sh           # report only
#   GCP_REGION=<region> scripts/set_artifact_cleanup_policy.sh --apply   # set the policy
#
# Needs a gcloud session with artifactregistry.repositories.update and read
# access to Cloud Run. Deliberately NOT a CI step, for the same reason
# grant_scheduler_iam.sh isn't: the deploy service account is scoped to
# pushing images and deploying, and widening it permanently to perform a
# one-time repo setting would be the wrong trade.
set -euo pipefail

PROJECT_ID="gen-lang-client-0153967509"
REPO="amlkit"
SERVICE="amlkit"

KEEP_COUNT=10
DELETE_OLDER_THAN_DAYS=30

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

if [[ -z "${GCP_REGION:-}" ]]; then
  echo "Set GCP_REGION first. It is a GitHub Actions repo variable" >&2
  echo "(vars.GCP_REGION); guessing it here would either fail confusingly or," >&2
  echo "worse, silently describe a different repository." >&2
  echo "" >&2
  echo "Repositories on this project:" >&2
  gcloud artifacts repositories list --project "$PROJECT_ID" 2>/dev/null || true
  exit 1
fi
REGION="$GCP_REGION"
REPO_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "== Reading image versions from ${REPO_PATH} =="
gcloud artifacts docker images list "$REPO_PATH" \
  --include-tags --format=json --project "$PROJECT_ID" > "$WORK/images.json"

echo "== Reading Cloud Run service and revisions (${SERVICE} / ${REGION}) =="
# Both are best-effort: a service that does not exist yet is a legitimate
# state (nothing deployed), and the check below treats "no in-use images
# found" as a reason to stop rather than a reason to proceed -- failing
# toward not deleting.
gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format=json > "$WORK/service.json" 2>/dev/null || echo '{}' > "$WORK/service.json"
gcloud run revisions list --service "$SERVICE" --region "$REGION" --project "$PROJECT_ID" \
  --format=json > "$WORK/revisions.json" 2>/dev/null || echo '[]' > "$WORK/revisions.json"

# `|| CHECK_STATUS=$?` rather than a bare call: under `set -e` a non-zero exit
# from the checker would abort the script before its status could be read, so
# the "report only" path (3) would look like a crash and --apply could never
# reach the policy write.
CHECK_STATUS=0
python3 - "$WORK" "$KEEP_COUNT" "$DELETE_OLDER_THAN_DAYS" "$APPLY" <<'PY' || CHECK_STATUS=$?
import json, sys, datetime as dt

work, keep_count, older_days, apply_mode = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4] == "1"

images = json.load(open(f"{work}/images.json"))
service = json.load(open(f"{work}/service.json"))
revisions = json.load(open(f"{work}/revisions.json"))


def parse_ts(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def digest_of(ref):
    """Pull the sha256:... out of an image reference, if it carries one."""
    return ref.split("@", 1)[1] if ref and "@" in ref else None


# ---- what the policy would keep vs delete ---------------------------------
now = dt.datetime.now(dt.timezone.utc)
rows = []
for img in images:
    created = parse_ts(img.get("createTime") or img.get("create_time"))
    rows.append({
        "version": img.get("version") or "",
        "tags": img.get("tags") or "",
        "created": created,
        # A version with no parseable timestamp cannot be shown to be older
        # than the window, so it is treated as recent. Fail toward keeping.
        "age_days": (now - created).days if created else -1,
    })

rows.sort(key=lambda r: r["created"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
for i, r in enumerate(rows):
    if i < keep_count:
        r["verdict"], r["why"] = "KEEP", f"one of the {keep_count} most recent"
    elif r["age_days"] < 0:
        r["verdict"], r["why"] = "KEEP", "no usable createTime; not shown to be old"
    elif r["age_days"] >= older_days:
        r["verdict"], r["why"] = "DELETE", f"{r['age_days']}d old"
    else:
        r["verdict"], r["why"] = "KEEP", f"{r['age_days']}d old, under {older_days}d"

# ---- what Cloud Run is actually relying on --------------------------------
def as_pct(value):
    """Traffic percent, coerced. Anything unparseable counts as SERVING.

    A type surprise from a future gcloud must not be the reason an in-use
    image loses its protection, so an unreadable percent is treated as live
    traffic rather than as zero.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return 100


traffic = {t.get("revisionName"): as_pct(t.get("percent", 0))
           for t in (service.get("status", {}) or {}).get("traffic", []) or []}

in_use = {}      # digest -> description, for anything with live traffic
known = {}       # digest -> description, for every revision that still exists
for rev in revisions:
    name = (rev.get("metadata", {}) or {}).get("name")
    status = rev.get("status", {}) or {}
    spec = rev.get("spec", {}) or {}
    containers = spec.get("containers") or []
    ref = containers[0].get("image") if containers else None
    digest = status.get("imageDigest") or digest_of(ref)
    if not digest:
        continue
    pct = traffic.get(name, 0) or 0
    known[digest] = f"{name}"
    if pct > 0:
        in_use[digest] = f"{name} ({pct}% of traffic)"

# ---- report ---------------------------------------------------------------
print()
print(f"{'VERDICT':8} {'AGE':>6}  {'DIGEST':22} TAGS / NOTE")
print("-" * 78)
for r in rows:
    digest = r["version"]
    marker = ""
    if digest in in_use:
        marker = f"  <== SERVING: {in_use[digest]}"
    elif digest in known:
        marker = f"  <- revision {known[digest]} (no traffic)"
    age = f"{r['age_days']}d" if r["age_days"] >= 0 else "?"
    print(f"{r['verdict']:8} {age:>6}  {digest[:22]:22} {r['tags'] or r['why']}{marker}")

to_delete = [r for r in rows if r["verdict"] == "DELETE"]
print()
print(f"Would keep {len(rows) - len(to_delete)}, delete {len(to_delete)} of {len(rows)} versions.")

# ---- the safety gate ------------------------------------------------------
problems = []
delete_digests = {r["version"] for r in to_delete}

serving_at_risk = sorted(delete_digests & set(in_use))
if serving_at_risk:
    for d in serving_at_risk:
        problems.append(f"image serving live traffic would be deleted: {d} -- {in_use[d]}")

if not in_use:
    problems.append(
        "could not identify any image serving traffic. That may just mean "
        "nothing is deployed yet, but it also means this check proved "
        "nothing, so it will not wave the deletion through."
    )

rollback_at_risk = sorted((delete_digests & set(known)) - set(in_use))
if rollback_at_risk:
    print()
    print("NOTE: these are referenced by revisions that exist but carry no")
    print("traffic. Deleting them does not break serving, but it does remove")
    print("the ability to roll traffic back onto them:")
    for d in rollback_at_risk:
        print(f"  - {d}  ({known[d]})")

if problems:
    print()
    print("REFUSING TO APPLY:")
    for p in problems:
        print(f"  ! {p}")
    print()
    print("Nothing has been changed. Investigate before re-running.")
    sys.exit(2)

print()
print("SAFE: every image with live traffic is in the keep set.")
if not apply_mode:
    print()
    print("Report only. Re-run with --apply to set the policy.")
    sys.exit(3)
PY

# 3 = report clean, not applying. 2 = unsafe, refused. 0 = clean and --apply
# was requested. Only 0 continues to the policy write.
if [[ $CHECK_STATUS -eq 3 ]]; then
  exit 0
elif [[ $CHECK_STATUS -ne 0 ]]; then
  exit $CHECK_STATUS
fi

echo ""
echo "== Applying cleanup policy (keep ${KEEP_COUNT} most recent, delete older than ${DELETE_OLDER_THAN_DAYS}d) =="

POLICY_FILE="$(mktemp)"
trap 'rm -f "$POLICY_FILE"; rm -rf "$WORK"' EXIT
cat > "$POLICY_FILE" <<JSON
[
  {
    "name": "keep-recent",
    "action": {"type": "Keep"},
    "mostRecentVersions": {"keepCount": ${KEEP_COUNT}}
  },
  {
    "name": "delete-old",
    "action": {"type": "Delete"},
    "condition": {"olderThan": "${DELETE_OLDER_THAN_DAYS}d"}
  }
]
JSON

# Where an artifact matches both a Keep and a Delete policy it is kept, so the
# 10 most recent survive even when older than 30 days.
#
# NOTE the delete condition has NO "tagState". Google's own example pairs
# olderThan with "tagState": "untagged", and copying that here would produce a
# policy that looks right in the console and deletes nothing at all: every
# image this pipeline pushes is tagged with a commit SHA, so there are no
# untagged versions to collect.
gcloud artifacts repositories set-cleanup-policies "$REPO" \
  --location "$REGION" \
  --project "$PROJECT_ID" \
  --policy="$POLICY_FILE" \
  --no-dry-run

echo ""
echo "== Policies now set =="
gcloud artifacts repositories describe "$REPO" \
  --location "$REGION" --project "$PROJECT_ID" \
  --format="value(cleanupPolicies)"

echo ""
echo "========================================================================"
echo "DONE. Old images are pruned automatically from here."
echo ""
echo "Cleanup runs on Artifact Registry's own schedule, not immediately, so"
echo "the repo will not shrink the moment this exits. Re-run this script"
echo "without --apply in a few days to see what actually went."
echo "========================================================================"
