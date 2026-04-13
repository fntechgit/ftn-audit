"""Audit emission strategies — async OTLP via Celery or Noop."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import transaction

from ftn_audit.constants import (
    DEFAULT_AUDIT_ENABLED,
    DEFAULT_DELIVERY_MODE,
    DELIVERY_MODE_NOOP,
    DELIVERY_MODE_SYNC,
    LOGGER_AUDIT,
    SETTING_AUDIT_ENABLED,
    SETTING_AUDIT_DELIVERY_MODE,
    TASK_EMIT_AUDIT_LOG,
)
from ftn_audit.serialization import make_json_safe

logger = logging.getLogger(LOGGER_AUDIT)


class NoopAuditStrategy:
    """Does nothing — used when AUDIT_ENABLED=False."""

    def emit(self, description: str, attributes: Dict[str, Any]) -> None:
        pass


class OtlpAuditStrategy:
    """Formats the audit event and enqueues it via Celery for OTLP delivery."""

    def emit(self, description: str, attributes: Dict[str, Any]) -> None:
        payload = {
            "description": description,
            "attributes": make_json_safe(attributes),
            "timestamp_ns": time.time_ns(),
        }
        try:
            transaction.on_commit(lambda: _enqueue_async(payload))
        except Exception:
            # Audit errors must never bubble into request execution.
            logger.exception("Unable to register audit on_commit callback. Dropping event.")


_strategy_instance: Optional[object] = None
_strategy_lock = threading.Lock()


def get_audit_strategy():
    global _strategy_instance
    if _strategy_instance is not None:
        return _strategy_instance

    with _strategy_lock:
        if _strategy_instance is not None:
            return _strategy_instance

        enabled = getattr(settings, SETTING_AUDIT_ENABLED, DEFAULT_AUDIT_ENABLED)
        delivery_mode = getattr(settings, SETTING_AUDIT_DELIVERY_MODE, DEFAULT_DELIVERY_MODE)
        if (not enabled) or delivery_mode == DELIVERY_MODE_NOOP:
            _strategy_instance = NoopAuditStrategy()
        else:
            if delivery_mode == DELIVERY_MODE_SYNC:
                logger.warning(
                    "AUDIT_DELIVERY_MODE='sync' is not supported. "
                    "Forcing async Celery emission for safety."
                )
            _strategy_instance = OtlpAuditStrategy()
    return _strategy_instance


def reset_audit_strategy() -> None:
    """Clear cached strategy instance (useful for tests and dynamic reconfiguration)."""
    global _strategy_instance
    with _strategy_lock:
        _strategy_instance = None


def _enqueue_async(payload: Dict[str, Any]) -> None:
    from ftn_audit.tasks import emit_audit_log_task

    try:
        emit_audit_log_task.delay(payload)
    except Exception:
        logger.exception(
            "Unable to enqueue task '%s'. "
            "Check Celery app autodiscovery and worker startup. "
            "Expected: app.autodiscover_tasks() and 'ftn_audit' in INSTALLED_APPS. "
            "Dropping audit event.",
            TASK_EMIT_AUDIT_LOG,
        )
