"""Celery task for async OTLP delivery of audit log records."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from celery import shared_task

logger = logging.getLogger("audit.otlp")


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=5,
    name="ftn_audit.emit_audit_log",
)
def emit_audit_log_task(self, payload: Dict[str, Any]) -> None:
    """Deliver a single audit record via OpenTelemetry Logs API."""
    try:
        from opentelemetry._logs import get_logger_provider

        otel_logger = get_logger_provider().get_logger("ftn_audit")
        otel_logger.emit(
            _build_log_record(payload)
        )
        logger.debug("Audit log emitted: %s", payload.get("description", ""))
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        # Final failure — log locally so the event is not silently lost
        logger.error(
            "Failed to emit audit log after %d retries: %s | payload=%s",
            self.max_retries,
            exc,
            json.dumps(payload, default=str),
        )


def _build_log_record(payload: Dict[str, Any]):
    """Build an OTel LogRecord from our audit payload."""
    from opentelemetry._logs import LogRecord, SeverityNumber

    return LogRecord(
        body=payload.get("description", ""),
        severity_number=SeverityNumber.INFO,
        severity_text="INFO",
        attributes=_flatten_attributes(payload.get("attributes", {})),
    )


def _flatten_attributes(attrs: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    """Flatten nested dicts into dot-separated keys with string values."""
    flat: Dict[str, str] = {}
    for key, value in attrs.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            flat.update(_flatten_attributes(value, full_key))
        else:
            flat[full_key] = json.dumps(value, default=str) if not isinstance(value, str) else value
    return flat
