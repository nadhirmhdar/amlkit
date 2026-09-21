"""Background job dispatcher with pluggable backends.

Two backends, selected by env AMLKIT_TASKS_BACKEND:
- "inline" (default): runs the job function synchronously in-process.
  Right for local dev, tests, and single-machine deploys.
- "cloudtasks": enqueues to Google Cloud Tasks for reliable async
  execution on Cloud Run. Requires env vars for project, queue, etc.

The dispatcher enforces a PII firewall: payloads may only contain IDs
and control fields, never names, emails, or document numbers. The task
handler re-loads data from the database using org_id-scoped queries.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Callable

log = logging.getLogger("amlkit.jobs")

# Fields that must never appear in a Cloud Tasks payload — they contain
# PII that would be visible in Cloud Logging and the Tasks console.
_PII_FIELDS = frozenset({
    "name", "name_arabic", "full_name", "email", "phone",
    "passport", "emirates_id", "id_number", "address",
    "birth_date", "date_of_birth", "nationality",
    "counterparty_name",
})

# Fields allowed in payloads (whitelist approach for extra safety)
_ALLOWED_FIELDS = frozenset({
    "job_name", "org_id", "customer_id", "ubo_id", "screening_id",
    "alert_id", "report_id", "dataset_key", "trigger", "actor",
    "window_months", "limit", "idempotency_key",
})


def _check_payload_pii(payload: dict[str, Any]) -> None:
    """Raise ValueError if payload contains PII fields."""
    pii_found = set(payload.keys()) & _PII_FIELDS
    if pii_found:
        raise ValueError(
            f"PII fields not allowed in job payload: {', '.join(sorted(pii_found))}"
        )


def validate_task_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an incoming task handler payload."""
    if "job_name" not in payload:
        raise ValueError("job_name is required")
    if "org_id" not in payload:
        raise ValueError("org_id is required")
    _check_payload_pii(payload)
    return payload


class InlineBackend:
    """Runs jobs synchronously in the current process."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable] = {}
        self._jobs: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}

    def register(self, job_name: str, handler: Callable) -> None:
        self._handlers[job_name] = handler

    def dispatch(
        self,
        job_name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> str:
        _check_payload_pii(payload)

        if job_name not in self._handlers:
            raise ValueError(f"Unknown job: {job_name}")

        if idempotency_key and idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key]

        job_id = str(uuid.uuid4())

        if idempotency_key:
            self._idempotency[idempotency_key] = job_id

        self._jobs[job_id] = {"status": "pending", "result": None, "error": None}

        try:
            result = self._handlers[job_name](payload)
            self._jobs[job_id] = {
                "status": "complete",
                "result": result,
                "error": None,
            }
        except Exception as exc:
            log.exception("Job %s (id=%s) failed: %s", job_name, job_id, exc)
            self._jobs[job_id] = {
                "status": "failed",
                "result": None,
                "error": str(exc),
            }

        return job_id

    def get_status(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)


class CloudTasksBackend:
    """Enqueues jobs to Google Cloud Tasks.

    Required env vars (passed as `env` dict for testability):
    - AMLKIT_TASKS_PROJECT: GCP project ID
    - AMLKIT_TASKS_QUEUE: Cloud Tasks queue name
    - AMLKIT_TASKS_LOCATION: region (default me-central1)
    - AMLKIT_TASKS_TARGET_URL: base URL for the task handler
    - AMLKIT_TASKS_SERVICE_ACCOUNT: service account for OIDC token
    """

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env or dict(os.environ)
        self._client: Any = None
        self._jobs: dict[str, dict[str, Any]] = {}
        self._idempotency: dict[str, str] = {}

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import tasks_v2
            self._client = tasks_v2.CloudTasksClient()
        return self._client

    def _queue_path(self) -> str:
        client = self._get_client()
        return client.queue_path(
            self._env["AMLKIT_TASKS_PROJECT"],
            self._env.get("AMLKIT_TASKS_LOCATION", "me-central1"),
            self._env["AMLKIT_TASKS_QUEUE"],
        )

    def register(self, job_name: str, handler: Callable) -> None:
        pass  # handlers run on the receiving end, not here

    def dispatch(
        self,
        job_name: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> str:
        _check_payload_pii(payload)

        if idempotency_key and idempotency_key in self._idempotency:
            return self._idempotency[idempotency_key]

        job_id = str(uuid.uuid4())

        if idempotency_key:
            self._idempotency[idempotency_key] = job_id

        client = self._get_client()
        queue_path = self._queue_path()

        target_url = self._env["AMLKIT_TASKS_TARGET_URL"].rstrip("/")
        handler_url = f"{target_url}/system/tasks/{job_name}"

        body = json.dumps({
            "job_name": job_name,
            "job_id": job_id,
            **payload,
        }).encode("utf-8")

        task = {
            "http_request": {
                "http_method": "POST",
                "url": handler_url,
                "headers": {"Content-Type": "application/json"},
                "body": body,
                "oidc_token": {
                    "service_account_email": self._env["AMLKIT_TASKS_SERVICE_ACCOUNT"],
                    "audience": target_url,
                },
            }
        }

        created = client.create_task(request={"parent": queue_path, "task": task})
        log.info("Cloud Task created: %s for job %s (id=%s)", created.name, job_name, job_id)

        self._jobs[job_id] = {"status": "pending", "result": None, "error": None}

        return job_id

    def get_status(self, job_id: str) -> dict[str, Any] | None:
        return self._jobs.get(job_id)

    def mark_complete(self, job_id: str, result: Any = None) -> None:
        self._jobs[job_id] = {"status": "complete", "result": result, "error": None}

    def mark_failed(self, job_id: str, error: str) -> None:
        self._jobs[job_id] = {"status": "failed", "result": None, "error": error}


# ---------------------------------------------------------------- module-level singleton

_backend: InlineBackend | CloudTasksBackend | None = None


def get_backend() -> InlineBackend | CloudTasksBackend:
    """Return the configured backend singleton."""
    global _backend
    if _backend is None:
        kind = os.environ.get("AMLKIT_TASKS_BACKEND", "inline").lower()
        if kind == "cloudtasks":
            _backend = CloudTasksBackend()
        else:
            _backend = InlineBackend()
    return _backend


def dispatch(
    job_name: str,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> str:
    """Dispatch a job through the configured backend."""
    return get_backend().dispatch(job_name, payload, idempotency_key=idempotency_key)


def get_status(job_id: str) -> dict[str, Any] | None:
    """Check status of a dispatched job."""
    return get_backend().get_status(job_id)
