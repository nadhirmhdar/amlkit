"""Structured JSON logging with request-ID correlation.

Every log line carries the current request's ID when available, so errors and
audit events can be traced back to the originating request without reading the
entire log linearly.
"""

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

# Context variables for request correlation and Cloud Logging
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)
org_id_var: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "org_id", default=None
)
trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)
span_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "span_id", default=None
)


class StructuredFormatter(logging.Formatter):
    """JSON formatter that emits Cloud Logging LogEntry-shaped structured logs.

    Applies PII redaction to message and extra fields so that Emirates
    IDs, emails, and passport numbers never appear in log output.
    """

    def format(self, record: logging.LogRecord) -> str:
        from .pii import redact

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,  # Keep for backwards compatibility
            "severity": record.levelname,  # Cloud Logging standard field
            "logger": record.name,
            "message": redact(record.getMessage()),
        }

        # Add Cloud Logging sourceLocation
        log_data["logging.googleapis.com/sourceLocation"] = {
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
        }

        # Add Cloud Logging labels
        labels: dict[str, str] = {}
        request_id = request_id_var.get()
        if request_id:
            labels["request_id"] = request_id
            log_data["request_id"] = request_id  # Keep for backwards compat

        org_id = org_id_var.get()
        if org_id is not None:
            labels["org_id"] = str(org_id)

        if labels:
            log_data["logging.googleapis.com/labels"] = labels

        # Add Cloud Logging trace context
        trace_id = trace_id_var.get()
        if trace_id:
            gcp_project = os.environ.get("GCP_PROJECT_ID", "unknown-project")
            log_data["logging.googleapis.com/trace"] = f"projects/{gcp_project}/traces/{trace_id}"

        span_id = span_id_var.get()
        if span_id:
            log_data["logging.googleapis.com/spanId"] = span_id

        if record.exc_info:
            log_data["exception"] = redact(self.formatException(record.exc_info))

        if hasattr(record, "extra_fields"):
            extras = record.extra_fields
            log_data.update(
                {k: redact(str(v)) if isinstance(v, str) else v
                 for k, v in extras.items()}
            )

        return json.dumps(log_data, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the application."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Ensure amlkit loggers use the root config
    for logger_name in ["amlkit", "amlkit.scheduler", "amlkit.api"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.propagate = True


def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID for the current context."""
    request_id_var.set(request_id)


def clear_request_id() -> None:
    """Clear the request ID from the current context."""
    request_id_var.set(None)


def get_org_id() -> int | None:
    """Get the current organization ID from context."""
    return org_id_var.get()


def set_org_id(org_id: int | None) -> None:
    """Set the organization ID for the current context."""
    org_id_var.set(org_id)


def get_trace_id() -> str | None:
    """Get the current trace ID from context."""
    return trace_id_var.get()


def set_trace_id(trace_id: str | None) -> None:
    """Set the trace ID for the current context."""
    trace_id_var.set(trace_id)


def get_span_id() -> str | None:
    """Get the current span ID from context."""
    return span_id_var.get()


def set_span_id(span_id: str | None) -> None:
    """Set the span ID for the current context."""
    span_id_var.set(span_id)
