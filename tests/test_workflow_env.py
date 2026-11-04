"""Workflow wiring: the CI source checks must receive the EU FSF token."""
import re
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github/workflows/source-canary.yml"


def _job_block(name: str) -> str:
    text = WF.read_text()
    m = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][a-z-]*:\n|\Z)", text, re.S | re.M)
    assert m, f"job {name} not found"
    return m.group(1)


def test_sources_and_heartbeat_jobs_get_eu_fsf_token():
    for job in ("sources", "heartbeat"):
        block = _job_block(job)
        assert "AMLKIT_EU_FSF_TOKEN: ${{ secrets.EU_FSF_TOKEN }}" in block, job


def test_deploy_job_still_passes_eu_fsf_token():
    assert "AMLKIT_EU_FSF_TOKEN: ${{ secrets.EU_FSF_TOKEN }}" in _job_block("deploy")
