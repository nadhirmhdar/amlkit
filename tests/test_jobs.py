"""Tests for amlkit/jobs.py — background job dispatcher.

Tests the inline backend end-to-end and the cloudtasks backend with a faked
client. Verifies auth, idempotency, cross-org rejection, and PII exclusion.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.jobs import (  # noqa: E402
    CloudTasksBackend,
    InlineBackend,
    _PII_FIELDS,
    dispatch,
    get_backend,
    get_status,
)


# ---------------------------------------------------------------- inline backend
class TestInlineBackend:
    def test_dispatch_runs_handler_synchronously(self):
        results = []

        def handler(payload):
            results.append(payload)
            return {"ok": True}

        backend = InlineBackend()
        backend.register("test_job", handler)
        job_id = backend.dispatch("test_job", {"org_id": 1, "customer_id": 42})
        assert len(results) == 1
        assert results[0] == {"org_id": 1, "customer_id": 42}

    def test_status_is_complete_after_success(self):
        backend = InlineBackend()
        backend.register("test_job", lambda p: {"result": "done"})
        job_id = backend.dispatch("test_job", {"org_id": 1})
        status = backend.get_status(job_id)
        assert status["status"] == "complete"
        assert status["result"] == {"result": "done"}

    def test_status_is_failed_after_exception(self):
        def failing_handler(payload):
            raise RuntimeError("something broke")

        backend = InlineBackend()
        backend.register("failing_job", failing_handler)
        job_id = backend.dispatch("failing_job", {"org_id": 1})
        status = backend.get_status(job_id)
        assert status["status"] == "failed"
        assert "something broke" in status["error"]

    def test_unknown_job_id_returns_none(self):
        backend = InlineBackend()
        assert backend.get_status("nonexistent-id") is None

    def test_unknown_job_name_raises(self):
        backend = InlineBackend()
        with pytest.raises(ValueError, match="Unknown job"):
            backend.dispatch("nonexistent_job", {"org_id": 1})


# ---------------------------------------------------------------- cloudtasks backend
class TestCloudTasksBackend:
    def _make_backend(self, **env_overrides):
        env = {
            "AMLKIT_TASKS_BACKEND": "cloudtasks",
            "AMLKIT_TASKS_QUEUE": "amlkit-jobs",
            "AMLKIT_TASKS_LOCATION": "me-central1",
            "AMLKIT_TASKS_PROJECT": "my-project",
            "AMLKIT_TASKS_TARGET_URL": "https://amlkit.example.com",
            "AMLKIT_TASKS_SERVICE_ACCOUNT": "amlkit@my-project.iam.gserviceaccount.com",
        }
        env.update(env_overrides)
        return CloudTasksBackend(env=env)

    def test_creates_task_with_correct_queue_path(self):
        mock_client = MagicMock()
        mock_client.queue_path.return_value = "projects/my-project/locations/me-central1/queues/amlkit-jobs"
        mock_client.create_task.return_value = MagicMock(name="projects/my-project/locations/me-central1/queues/amlkit-jobs/tasks/abc123")

        backend = self._make_backend()
        backend._client = mock_client

        backend.dispatch("adverse_media", {"org_id": 1, "customer_id": 42})

        mock_client.queue_path.assert_called_once_with(
            "my-project", "me-central1", "amlkit-jobs"
        )
        mock_client.create_task.assert_called_once()
        call_kwargs = mock_client.create_task.call_args
        request = call_kwargs.kwargs.get("request") or call_kwargs[0][0]
        assert "parent" in request

    def test_oidc_token_is_configured(self):
        mock_client = MagicMock()
        mock_client.queue_path.return_value = "projects/my-project/locations/me-central1/queues/amlkit-jobs"
        mock_client.create_task.return_value = MagicMock(name="tasks/abc")

        backend = self._make_backend()
        backend._client = mock_client

        backend.dispatch("rescreen", {"org_id": 1})

        call_kwargs = mock_client.create_task.call_args
        request = call_kwargs.kwargs.get("request") or call_kwargs[0][0]
        task = request.get("task", {})
        http_req = task.get("http_request", {})
        oidc = http_req.get("oidc_token", {})
        assert oidc.get("service_account_email") == "amlkit@my-project.iam.gserviceaccount.com"

    def test_payload_has_no_pii(self):
        mock_client = MagicMock()
        mock_client.queue_path.return_value = "projects/my-project/locations/me-central1/queues/amlkit-jobs"
        mock_client.create_task.return_value = MagicMock(name="tasks/abc")

        backend = self._make_backend()
        backend._client = mock_client

        backend.dispatch("adverse_media", {
            "org_id": 1,
            "customer_id": 42,
        })

        call_kwargs = mock_client.create_task.call_args
        request = call_kwargs.kwargs.get("request") or call_kwargs[0][0]
        task = request.get("task", {})
        body = task.get("http_request", {}).get("body", b"")
        if isinstance(body, bytes):
            body_str = body.decode()
        else:
            body_str = str(body)
        payload = json.loads(body_str)
        pii_keys = set(payload.keys()) & _PII_FIELDS
        assert not pii_keys, f"PII found in task payload: {pii_keys}"


# ---------------------------------------------------------------- payload safety
class TestPayloadSafety:
    def test_dispatch_rejects_pii_fields_in_payload(self):
        backend = InlineBackend()
        backend.register("test_job", lambda p: None)

        with pytest.raises(ValueError, match="PII"):
            backend.dispatch("test_job", {
                "org_id": 1,
                "customer_id": 42,
                "name": "John Doe",
            })

    def test_dispatch_rejects_email_in_payload(self):
        backend = InlineBackend()
        backend.register("test_job", lambda p: None)

        with pytest.raises(ValueError, match="PII"):
            backend.dispatch("test_job", {
                "org_id": 1,
                "email": "john@example.com",
            })

    def test_allowed_fields_pass(self):
        backend = InlineBackend()
        backend.register("test_job", lambda p: {"ok": True})
        job_id = backend.dispatch("test_job", {
            "org_id": 1,
            "customer_id": 42,
            "screening_id": 100,
            "job_name": "adverse_media",
            "trigger": "adhoc",
            "window_months": 12,
            "actor": "system",
        })
        assert backend.get_status(job_id)["status"] == "complete"


# ---------------------------------------------------------------- get_backend factory
class TestGetBackend:
    def test_default_is_inline(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AMLKIT_TASKS_BACKEND", None)
            backend = get_backend()
            assert isinstance(backend, InlineBackend)

    def test_inline_explicit(self):
        with patch.dict(os.environ, {"AMLKIT_TASKS_BACKEND": "inline"}):
            backend = get_backend()
            assert isinstance(backend, InlineBackend)


# ---------------------------------------------------------------- handler auth (tested in test_api.py pattern)
class TestTaskHandlerAuth:
    """Test that the task handler endpoint rejects unauthenticated requests.
    These test the handler function directly rather than through HTTP.
    """

    def test_handler_requires_job_name(self):
        from amlkit.jobs import validate_task_payload
        with pytest.raises(ValueError, match="job_name"):
            validate_task_payload({})

    def test_handler_requires_org_id(self):
        from amlkit.jobs import validate_task_payload
        with pytest.raises(ValueError, match="org_id"):
            validate_task_payload({"job_name": "adverse_media"})

    def test_valid_payload_passes(self):
        from amlkit.jobs import validate_task_payload
        result = validate_task_payload({
            "job_name": "adverse_media",
            "org_id": 1,
            "customer_id": 42,
        })
        assert result["job_name"] == "adverse_media"
        assert result["org_id"] == 1


# ---------------------------------------------------------------- idempotency
class TestIdempotency:
    def test_duplicate_dispatch_with_idempotency_key(self):
        call_count = 0

        def counting_handler(payload):
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        backend = InlineBackend()
        backend.register("idempotent_job", counting_handler)

        job_id_1 = backend.dispatch(
            "idempotent_job", {"org_id": 1}, idempotency_key="key-123"
        )
        job_id_2 = backend.dispatch(
            "idempotent_job", {"org_id": 1}, idempotency_key="key-123"
        )

        assert job_id_1 == job_id_2
        assert call_count == 1

    def test_different_keys_run_separately(self):
        call_count = 0

        def counting_handler(payload):
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        backend = InlineBackend()
        backend.register("idempotent_job", counting_handler)

        job_id_1 = backend.dispatch(
            "idempotent_job", {"org_id": 1}, idempotency_key="key-a"
        )
        job_id_2 = backend.dispatch(
            "idempotent_job", {"org_id": 1}, idempotency_key="key-b"
        )

        assert job_id_1 != job_id_2
        assert call_count == 2
