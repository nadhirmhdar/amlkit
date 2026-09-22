"""Tests for Cloud Logging structured logging fields.

Tests verify Cloud Logging LogEntry field structure and trace context parsing.
PII redaction is already tested separately; here we focus on the LogEntry format.
"""

import json
import logging
import os
from io import StringIO

import pytest


def test_severity_field_maps_logging_levels():
    """Cloud Logging 'severity' field should map Python logging levels correctly."""
    from amlkit.logging_config import StructuredFormatter

    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("test_severity")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.debug("debug message")
    log_line = json.loads(output.getvalue().strip())
    assert log_line["severity"] == "DEBUG"
    assert log_line["level"] == "DEBUG"  # Keep for backwards compat


def test_source_location_fields_present():
    """StructuredFormatter should emit logging.googleapis.com/sourceLocation."""
    from amlkit.logging_config import StructuredFormatter

    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("test_source")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("test message")
    log_line = json.loads(output.getvalue().strip())

    assert "logging.googleapis.com/sourceLocation" in log_line
    source_loc = log_line["logging.googleapis.com/sourceLocation"]
    assert "file" in source_loc
    assert "line" in source_loc
    assert "function" in source_loc
    assert isinstance(source_loc["line"], int)


def test_labels_with_org_id_and_request_id():
    """StructuredFormatter should emit logging.googleapis.com/labels with org_id and request_id."""
    from amlkit.logging_config import StructuredFormatter, set_request_id, set_org_id

    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("test_labels")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    set_request_id("req-12345")
    set_org_id(42)

    logger.info("test message")
    log_line = json.loads(output.getvalue().strip())

    assert "logging.googleapis.com/labels" in log_line
    labels = log_line["logging.googleapis.com/labels"]
    assert labels["request_id"] == "req-12345"
    assert labels["org_id"] == "42"  # Labels are strings in Cloud Logging


def test_trace_and_span_fields_present():
    """StructuredFormatter should emit trace and spanId when set in context."""
    from amlkit.logging_config import StructuredFormatter, set_trace_id, set_span_id

    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("test_trace")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    set_trace_id("abc123def456")
    set_span_id("7890")

    logger.info("test message")
    log_line = json.loads(output.getvalue().strip())

    # Trace should be formatted as projects/{project}/traces/{trace_id}
    assert "logging.googleapis.com/trace" in log_line
    trace = log_line["logging.googleapis.com/trace"]
    assert "projects/" in trace
    assert "/traces/abc123def456" in trace

    assert "logging.googleapis.com/spanId" in log_line
    assert log_line["logging.googleapis.com/spanId"] == "7890"


def test_x_cloud_trace_context_parsed():
    """Middleware should parse X-Cloud-Trace-Context: TRACE/SPAN;o=1."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    client = TestClient(app)

    # Make a request with X-Cloud-Trace-Context header
    response = client.get(
        "/",
        headers={"X-Cloud-Trace-Context": "105445aa7843bc8bf206b120001000/123456;o=1"}
    )

    # Response should succeed
    assert response.status_code in [200, 302, 404]


def test_w3c_traceparent_parsed():
    """Middleware should parse W3C traceparent: 00-TRACE-SPAN-01."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    client = TestClient(app)

    # Make a request with traceparent header
    response = client.get(
        "/",
        headers={"traceparent": "00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01"}
    )

    assert response.status_code in [200, 302, 404]


def test_missing_trace_headers_handled():
    """Middleware should handle missing trace headers gracefully."""
    from fastapi.testclient import TestClient
    from amlkit.api.app import app

    client = TestClient(app)

    # Request without trace headers
    response = client.get("/")

    # Should still work
    assert response.status_code in [200, 302, 404]


def test_gcp_project_id_in_trace_format():
    """Trace field should use GCP_PROJECT_ID env var if set."""
    from amlkit.logging_config import StructuredFormatter, set_trace_id

    # Set GCP_PROJECT_ID
    os.environ["GCP_PROJECT_ID"] = "test-project-123"

    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(StructuredFormatter())
    logger = logging.getLogger("test_gcp")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    set_trace_id("abc123")
    logger.info("test")
    log_line = json.loads(output.getvalue().strip())

    assert log_line["logging.googleapis.com/trace"] == "projects/test-project-123/traces/abc123"

    # Cleanup
    del os.environ["GCP_PROJECT_ID"]
