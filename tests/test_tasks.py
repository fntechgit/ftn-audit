from __future__ import annotations

from unittest.mock import patch

import pytest
from opentelemetry.trace import TraceFlags

from ftn_audit.tasks import _build_log_record
from ftn_audit.tasks import emit_audit_log
from ftn_audit.tasks import emit_audit_log_task


def _in_memory_logger_provider():
    """A real SDK LoggerProvider whose records land in an in-memory exporter."""
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs import export
    from opentelemetry.sdk.resources import Resource

    # Renamed to InMemoryLogRecordExporter in SDK 1.39; the old name is gone in later releases.
    exporter_class = getattr(export, "InMemoryLogRecordExporter", None) or export.InMemoryLogExporter
    exporter = exporter_class()
    provider = LoggerProvider(resource=Resource.create({"service.name": "audited-service"}))
    provider.add_log_record_processor(export.SimpleLogRecordProcessor(exporter))
    return provider, exporter


def test_emit_audit_log_exports_the_record_through_the_installed_sdk():
    # Runs on the installed SDK without patching its classes: opentelemetry-sdk 1.39 removed
    # opentelemetry.sdk._logs.LogRecord, and every audit event then failed with ImportError.
    from opentelemetry.sdk.trace import TracerProvider

    provider, exporter = _in_memory_logger_provider()
    payload = {
        "description": "Updated cart #253",
        "attributes": {"audit.event_type": "update", "audit.changeset": {"status": {"old": "Open", "new": "CheckedOut"}}},
        "timestamp_ns": 123456789,
    }
    tracer = TracerProvider().get_tracer("ftn-audit-test")

    with patch("opentelemetry._logs.get_logger_provider", return_value=provider):
        with tracer.start_as_current_span("request") as span:
            emit_audit_log(payload)

    (exported,) = exporter.get_finished_logs()
    record = exported.log_record
    assert record.body == "Updated cart #253"
    assert record.timestamp == 123456789
    assert record.severity_text == "INFO"
    assert dict(record.attributes) == {
        "audit.event_type": "update",
        "audit.changeset.status.old": "Open",
        "audit.changeset.status.new": "CheckedOut",
    }
    assert record.trace_id == span.get_span_context().trace_id
    assert record.span_id == span.get_span_context().span_id


def _sdk_has_its_own_log_record():
    import opentelemetry.sdk._logs as sdk_logs

    return hasattr(sdk_logs, "LogRecord")


@pytest.mark.skipif(_sdk_has_its_own_log_record(), reason="SDK <= 1.38 exports its own LogRecord as built")
def test_emit_audit_log_carries_the_provider_resource_on_sdks_without_their_own_log_record():
    # From 1.39 the API record is wrapped with the provider's resource, which the OTLP exporter
    # serializes; a record reaching the exporter without one cannot be encoded.
    provider, exporter = _in_memory_logger_provider()

    with patch("opentelemetry._logs.get_logger_provider", return_value=provider):
        emit_audit_log({"description": "Created cart #1", "attributes": {}, "timestamp_ns": 1})

    (exported,) = exporter.get_finished_logs()
    assert exported.resource.attributes["service.name"] == "audited-service"


def test_build_log_record_forwards_timestamp():
    payload = {
        "description": "hello",
        "attributes": {"audit.event_type": "update"},
        "timestamp_ns": 123456789,
    }

    record = _build_log_record(payload)

    assert record.timestamp == 123456789


def test_build_log_record_extracts_trace_context_from_active_span():
    payload = {
        "description": "hello",
        "attributes": {"audit.event_type": "update"},
        "timestamp_ns": 123456789,
    }
    expected_trace_id = 0x1234567890ABCDEF1234567890ABCDEF
    expected_span_id = 0x1234567890ABCDEF
    expected_trace_flags = TraceFlags(0x01)
    span_context = type(
        "SpanContextMock",
        (),
        {
            "is_valid": True,
            "trace_id": expected_trace_id,
            "span_id": expected_span_id,
            "trace_flags": expected_trace_flags,
        },
    )()
    span = type(
        "SpanMock",
        (),
        {"get_span_context": lambda self: span_context},
    )()

    with patch("opentelemetry.trace.get_current_span", return_value=span):
        record = _build_log_record(payload)

    assert record.trace_id == expected_trace_id
    assert record.span_id == expected_span_id
    assert record.trace_flags == expected_trace_flags


def test_build_log_record_omits_none_attributes():
    # Elasticsearch maps changeset fields from their first value, so a "null" string in a field
    # first seen as a date gets the whole record rejected. A missing key means no value.
    payload = {
        "description": "Updated cart #253",
        "attributes": {
            "audit.event_type": "update",
            "user_id": None,
            "audit.changeset": {
                "status": {"old": "PendingPayment", "new": "Open"},
                "checkout_date": {"old": "2026-10-28T18:24:07+00:00", "new": None},
            },
        },
        "timestamp_ns": 123,
    }

    record = _build_log_record(payload)

    assert dict(record.attributes) == {
        "audit.event_type": "update",
        "audit.changeset.status.old": "PendingPayment",
        "audit.changeset.status.new": "Open",
        "audit.changeset.checkout_date.old": "2026-10-28T18:24:07+00:00",
    }


def test_build_log_record_keeps_serializing_other_values_as_json():
    payload = {
        "description": "Updated cart #253",
        "attributes": {"audit.changeset": {"raw_amount": {"old": 0, "new": 1500}, "locked": {"old": False, "new": True}}, "ids": [1, None]},
        "timestamp_ns": 123,
    }

    record = _build_log_record(payload)

    assert dict(record.attributes) == {
        "audit.changeset.raw_amount.old": "0",
        "audit.changeset.raw_amount.new": "1500",
        "audit.changeset.locked.old": "false",
        "audit.changeset.locked.new": "true",
        "ids": "[1, null]",
    }


def test_emit_audit_log_task_retries_on_transient_failure():
    payload = {"description": "retry me", "attributes": {}, "timestamp_ns": 123}
    task = emit_audit_log_task._get_current_object()
    original_retries = getattr(task.request, "retries", 0)
    task.request.retries = 0

    try:
        with patch("ftn_audit.tasks.emit_audit_log", side_effect=RuntimeError("otlp down")):
            with patch.object(task, "retry", side_effect=RuntimeError("retry-called")) as retry_mock:
                with pytest.raises(RuntimeError, match="retry-called"):
                    task.run(payload)

        retry_mock.assert_called_once()
        assert isinstance(retry_mock.call_args.kwargs.get("exc"), RuntimeError)
    finally:
        task.request.retries = original_retries


def test_emit_audit_log_task_stops_retry_after_max_retries(caplog):
    payload = {"description": "drop me", "attributes": {"a": 1}, "timestamp_ns": 123}
    task = emit_audit_log_task._get_current_object()
    original_retries = getattr(task.request, "retries", 0)
    task.request.retries = task.max_retries

    try:
        with patch("ftn_audit.tasks.emit_audit_log", side_effect=RuntimeError("otlp down")):
            with patch.object(task, "retry") as retry_mock:
                with caplog.at_level("ERROR", logger="audit.otlp"):
                    task.run(payload)

        retry_mock.assert_not_called()
        assert "Failed to emit audit log after" in caplog.text
    finally:
        task.request.retries = original_retries


def test_emit_audit_log_task_ignores_result_backend():
    assert emit_audit_log_task.ignore_result is True


def test_emit_audit_log_task_uses_late_ack_and_rejects_on_worker_lost():
    assert emit_audit_log_task.acks_late is True
    assert emit_audit_log_task.reject_on_worker_lost is True
