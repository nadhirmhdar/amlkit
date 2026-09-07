#!/bin/bash
# One-time setup: stop the Artifact Registry repo growing without bound.
#
# The deploy tags every image by ${{ github.sha }} (see .github/workflows/
# source-canary.yml) and nothing has ever deleted one. This image is not
# small -- python:3.11-slim plus the Google Cloud CLI, Tesseract with English
# AND Arabic language data, Graphviz and Litestream -- so at roughly 1 GB a
# deploy, a year of active development is a bill that grows forever for
# images that will never run again. Artifact Registry charges $0.10/GB/month
# beyond the free 0.5 GB.
#
# Run this once, from a terminal where `gcloud` is authenticated as an
# Owner/IAM Admin on the project (e.g. Cloud Shell). It is deliberately NOT
# a CI step, for the same reason the Cloud Scheduler API enable isn't (see
# grant_scheduler_iam.sh): setting a cleanup policy needs
# artifactregistry.repositories.update, and the deploy service account is
# intentionally scoped to pushing images and deploying, nothing broader.
# Widening that grant permanently to perform a one-time repo setting would
# be the wrong trade.
#
# The policy is idempotent -- re-running it overwrites with the same rules.
set -euo pipefail

PROJECT_ID="gen-lang-client-0153967509"
REPO="amlkit"

# Not defaulted: the region is a GitHub Actions repo variable (vars.GCP_REGION)
# and guessing it here would either fail confusingly or, worse, silently
# describe a different repo. Read it from the repo's Actions variables, or
# from `gcloud artifacts repositories list --project "$PROJECT_ID"`.
if [[ -z "${GCP_REGION:-}" ]]; then
  echo "Set GCP_REGION first, e.g.:" >&2
  echo "  GCP_REGION=\$(gcloud artifacts repositories list --project ${PROJECT_ID} \\" >&2
  echo "      --format='value(name)' --filter='name:${REPO}' | head -1) $0" >&2
  echo "" >&2
  echo "Repositories on this project:" >&2
  gcloud artifacts repositories list --project "$PROJECT_ID" 2>/dev/null || true
  exit 1
fi
REGION="$GCP_REGION"

# keep-recent: the last 10 images stay regardless of age, so a rollback
#   target always exists even during a quiet period with no deploys.
# delete-old: anything older than 30 days goes. Ordering does not matter --
#   where an artifact matches both a Keep and a Delete policy it is kept, so
#   the 10 most recent survive even when they are older than 30 days.
#
# NOTE the delete condition has NO "tagState". Google's own example pairs
# olderThan with "tagState": "untagged", and copying that here would produce
# a policy that looks right in the console and deletes nothing at all: every
# image this pipeline pushes is tagged with a commit SHA, so there are no
# untagged versions to collect. Omitting tagState is what makes the policy
# actually apply to the images that exist.
POLICY_FILE="$(mktemp)"
trap 'rm -f "$POLICY_FILE"' EXIT
cat > "$POLICY_FILE" <<'JSON'
[
  {
    "name": "keep-recent",
    "action": {"type": "Keep"},
    "mostRecentVersions": {"keepCount": 10}
  },
  {
    "name": "delete-old",
    "action": {"type": "Delete"},
    "condition": {"olderThan": "30d"}
  }
]
JSON

echo "== Current repo size =="
gcloud artifacts repositories describe "$REPO" \
  --location "$REGION" --project "$PROJECT_ID" \
  --format="value(name, sizeBytes)" || {
    echo "Could not describe ${REPO} in ${REGION}." >&2
    echo "Set GCP_REGION to the region the repo actually lives in and re-run." >&2
    exit 1
  }

echo ""
echo "== Applying cleanup policy (keep 10 most recent, delete older than 30d) =="
# --no-dry-run: without it the policy is recorded but never actually deletes
# anything, which looks identical to a working policy in the console and is
# exactly the sort of silent no-op this repo already got bitten by once (the
# litestream.yml that nothing executed -- see Dockerfile).
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
echo "DONE. Old images are now pruned automatically."
echo ""
echo "Cleanup runs on Artifact Registry's own schedule, not immediately, so"
echo "the repo will not shrink the moment this exits. Check back in a day."
echo "========================================================================"
