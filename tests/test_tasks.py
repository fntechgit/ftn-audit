from __future__ import annotations

from unittest.mock import patch

import pytest
from opentelemetry.trace import TraceFlags

from ftn_audit.tasks import _build_log_record
from ftn_audit.tasks import emit_audit_log_task


@pytest.fixture(autouse=True)
def _ensure_public_logrecord_symbol(monkeypatch):
    import opentelemetry.sdk._logs as logs_module

    if hasattr(logs_module, "LogRecord"):
        return

    from opentelemetry.sdk._logs._internal import LogRecord as InternalLogRecord

    monkeypatch.setattr(logs_module, "LogRecord", InternalLogRecord, raising=False)


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
