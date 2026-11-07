"""Workflow wiring: the CI source checks must receive the EU FSF token."""
import re
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github/workflows/source-canary.yml"


PR_GATED_TOKEN = ("AMLKIT_EU_FSF_TOKEN: ${{ github.event_name != 'pull_request' "
                  "&& secrets.EU_FSF_TOKEN || '' }}")


def _job_block(name: str) -> str:
    text = WF.read_text()
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)", text, re.S | re.M)
    assert m, f"job {name} not found"
    return m.group(1)


def test_sources_and_heartbeat_jobs_get_eu_fsf_token():
    for job in ("sources", "heartbeat"):
        block = _job_block(job)
        assert PR_GATED_TOKEN in block, job
        # never the bare secret in these two jobs (L-122 / CR-40)
        assert "AMLKIT_EU_FSF_TOKEN: ${{ secrets.EU_FSF_TOKEN }}" not in block, job


def test_deploy_job_still_passes_eu_fsf_token():
    assert "AMLKIT_EU_FSF_TOKEN: ${{ secrets.EU_FSF_TOKEN }}" in _job_block("deploy")


def test_pull_request_trigger_still_exists_so_the_gate_matters():
    assert re.search(r"^  pull_request:", WF.read_text(), re.M)


def test_token_is_empty_on_pull_requests_by_expression():
    # The only EU secret references outside deploy sit behind the PR gate.
    for job in ("sources", "heartbeat"):
        refs = re.findall(r"secrets\.EU_FSF_TOKEN", _job_block(job))
        assert len(refs) == 1 and PR_GATED_TOKEN in _job_block(job), job
