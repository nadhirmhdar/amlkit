"""Structured JSON logging with request-ID correlation.

Every log line carries the current request's ID when available, so errors and
audit events can be traced back to the originating request without reading the
entire log linearly.
"""

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Thread-local storage for the current request ID
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)


class StructuredFormatter(logging.Formatter):
    """JSON formatter that includes request_id when present.

    Applies PII redaction to message and extra fields so that Emirates
    IDs, emails, and passport numbers never appear in log output.
    """

    def format(self, record: logging.LogRecord) -> str:
        from .pii import redact

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }

        request_id = request_id_var.get()
        if request_id:
            log_data["request_id"] = request_id

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
