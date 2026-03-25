from __future__ import annotations

import threading
from unittest.mock import ANY, patch

from ftn_audit.strategy import NoopAuditStrategy, OtlpAuditStrategy, get_audit_strategy, reset_audit_strategy


def _reset_strategy_singleton():
    reset_audit_strategy()


def test_get_audit_strategy_returns_noop_when_disabled(settings):
    settings.AUDIT_ENABLED = False
    _reset_strategy_singleton()

    resolved = get_audit_strategy()

    assert isinstance(resolved, NoopAuditStrategy)


def test_get_audit_strategy_returns_otlp_when_enabled(settings):
    settings.AUDIT_ENABLED = True
    _reset_strategy_singleton()

    resolved = get_audit_strategy()

    assert isinstance(resolved, OtlpAuditStrategy)


def test_otlp_strategy_emits_on_commit_payload():
    callbacks = []

    with patch("django.db.transaction.on_commit", side_effect=lambda cb: callbacks.append(cb)):
        with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
            OtlpAuditStrategy().emit("Fntech logged in", {"audit.event_type": "login"})

            assert len(callbacks) == 1
            callbacks[0]()

    delay_mock.assert_called_once_with(
        {
            "description": "Fntech logged in",
            "attributes": {"audit.event_type": "login"},
            "timestamp_ns": ANY,
        }
    )


def test_get_audit_strategy_returns_noop_when_delivery_mode_noop(settings):
    settings.AUDIT_ENABLED = True
    settings.AUDIT_DELIVERY_MODE = "noop"
    _reset_strategy_singleton()

    resolved = get_audit_strategy()

    assert isinstance(resolved, NoopAuditStrategy)


def test_otlp_strategy_sync_mode_forces_async_enqueue(settings, caplog):
    callbacks = []
    settings.AUDIT_DELIVERY_MODE = "sync"

    with patch("django.db.transaction.on_commit", side_effect=lambda cb: callbacks.append(cb)):
        with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
            OtlpAuditStrategy().emit("Sync event", {"audit.event_type": "update"})
            assert len(callbacks) == 1
            with caplog.at_level("WARNING", logger="audit"):
                callbacks[0]()

    delay_mock.assert_called_once_with(
        {
            "description": "Sync event",
            "attributes": {"audit.event_type": "update"},
            "timestamp_ns": ANY,
        }
    )
    assert "Forcing async Celery emission for safety." in caplog.text


def test_reset_audit_strategy_resolves_new_instance(settings):
    settings.AUDIT_ENABLED = True
    _reset_strategy_singleton()
    first = get_audit_strategy()

    reset_audit_strategy()
    second = get_audit_strategy()

    assert isinstance(first, OtlpAuditStrategy)
    assert isinstance(second, OtlpAuditStrategy)
    assert first is not second


def test_otlp_strategy_enqueue_failure_logs_and_drops(settings, caplog):
    settings.AUDIT_DELIVERY_MODE = "celery"

    callbacks = []
    with patch("django.db.transaction.on_commit", side_effect=lambda cb: callbacks.append(cb)):
        with patch("ftn_audit.tasks.emit_audit_log_task.delay", side_effect=RuntimeError("broker down")):
            OtlpAuditStrategy().emit("Fallback me", {"audit.event_type": "update"})
            assert len(callbacks) == 1
            with caplog.at_level("ERROR", logger="audit"):
                callbacks[0]()

    assert "Dropping audit event." in caplog.text


def test_otlp_strategy_on_commit_registration_failure_is_swallowed(caplog):
    with patch("django.db.transaction.on_commit", side_effect=RuntimeError("tx broken")):
        with caplog.at_level("ERROR", logger="audit"):
            OtlpAuditStrategy().emit("Drop me", {"audit.event_type": "update"})

    assert "Unable to register audit on_commit callback. Dropping event." in caplog.text


def test_get_audit_strategy_initializes_singleton_once_under_concurrency(settings):
    settings.AUDIT_ENABLED = True
    _reset_strategy_singleton()

    results = []
    errors = []

    def _target():
        try:
            results.append(get_audit_strategy())
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    with patch("ftn_audit.strategy.OtlpAuditStrategy", side_effect=lambda: object()) as ctor:
        threads = [threading.Thread(target=_target) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert not errors
    assert len(results) == 12
    assert ctor.call_count == 1
    first = results[0]
    assert all(item is first for item in results)
