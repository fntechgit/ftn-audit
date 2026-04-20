"""Celery task for async OTLP delivery of audit log records."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from celery import shared_task

from ftn_audit.constants import (
    DEFAULT_TASK_MAX_RETRIES,
    DEFAULT_TASK_RETRY_DELAY_SECONDS,
    LOGGER_AUDIT_OTLP,
    OTEL_LOGGER_NAME,
    TASK_EMIT_AUDIT_LOG,
)

logger = logging.getLogger(LOGGER_AUDIT_OTLP)


def emit_audit_log(payload: Dict[str, Any]) -> None:
    """Deliver a single audit record via OpenTelemetry Logs API."""
    # OpenTelemetry Python currently exposes Logs API under `_logs` in 1.x.
    # Keep opentelemetry-api/opentelemetry-sdk pinned to <2.0 for compatibility.
    from opentelemetry._logs import get_logger_provider

    otel_logger = get_logger_provider().get_logger(OTEL_LOGGER_NAME)
    otel_logger.emit(_build_log_record(payload))


@shared_task(
    bind=True,
    acks_late=True,
    ignore_result=True,
    max_retries=DEFAULT_TASK_MAX_RETRIES,
    default_retry_delay=DEFAULT_TASK_RETRY_DELAY_SECONDS,
    name=TASK_EMIT_AUDIT_LOG,
    reject_on_worker_lost=True,
)
def emit_audit_log_task(self, payload: Dict[str, Any]) -> None:
    """Best-effort task that retries transient OTLP failures."""
    try:
        emit_audit_log(payload)
        logger.info("Audit log emitted: %s", payload.get("description", ""))
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        logger.error(
            "Failed to emit audit log after %d retries: %s | payload=%s",
            self.max_retries,
            exc,
            json.dumps(payload, default=str),
        )


def _build_log_record(payload: Dict[str, Any]):
    """Build an OTel LogRecord from our audit payload."""
    # Build the SDK log record type (not API type), otherwise exporters may
    # fail at serialization time expecting SDK fields such as `resource`.
    from opentelemetry._logs import SeverityNumber
    from opentelemetry import trace
    from opentelemetry.trace import INVALID_SPAN_ID, INVALID_TRACE_ID, TraceFlags
    from opentelemetry.sdk._logs import LogRecord

    span_context = trace.get_current_span().get_span_context()
    trace_id = INVALID_TRACE_ID
    span_id = INVALID_SPAN_ID
    trace_flags = TraceFlags(0x00)
    if span_context is not None and getattr(span_context, "is_valid", False):
        trace_id = span_context.trace_id
        span_id = span_context.span_id
        trace_flags = span_context.trace_flags

    return LogRecord(
        timestamp=payload.get("timestamp_ns"),
        trace_id=trace_id,
        span_id=span_id,
        trace_flags=trace_flags,
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
