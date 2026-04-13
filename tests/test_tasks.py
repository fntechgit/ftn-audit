from __future__ import annotations

from unittest.mock import patch

import pytest

from ftn_audit.tasks import _build_log_record
from ftn_audit.tasks import emit_audit_log_task


def test_build_log_record_forwards_timestamp():
    payload = {
        "description": "hello",
        "attributes": {"audit.event_type": "update"},
        "timestamp_ns": 123456789,
    }

    record = _build_log_record(payload)

    assert record.timestamp == 123456789


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
