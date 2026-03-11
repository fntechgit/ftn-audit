"""Audit emission strategies — OTLP or Noop."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger("audit")


class NoopAuditStrategy:
    """Does nothing — used when AUDIT_ENABLED=False."""

    def emit(self, description: str, attributes: Dict[str, Any]) -> None:
        pass


class OtlpAuditStrategy:
    """Formats the audit event and enqueues it via Celery for OTLP delivery."""

    def emit(self, description: str, attributes: Dict[str, Any]) -> None:
        from ftn_audit.jobs import emit_audit_log_task

        payload = {
            "description": description,
            "attributes": attributes,
        }
        from django.db import transaction

        transaction.on_commit(
            lambda: emit_audit_log_task.delay(payload)
        )


_strategy_instance: Optional[object] = None


def get_audit_strategy():
    global _strategy_instance
    if _strategy_instance is not None:
        return _strategy_instance

    enabled = getattr(settings, "AUDIT_ENABLED", True)
    if not enabled:
        _strategy_instance = NoopAuditStrategy()
    else:
        _strategy_instance = OtlpAuditStrategy()
    return _strategy_instance
