"""Celery helpers for predictable ftn-audit integration."""

from __future__ import annotations

import logging

from ftn_audit.constants import LOGGER_AUDIT, TASK_EMIT_AUDIT_LOG

logger = logging.getLogger(LOGGER_AUDIT)


def configure_celery_audit(celery_app) -> None:
    """
    Register ftn-audit tasks without requiring manual task imports.

    Recommended usage in consumer services:
      configure_celery_audit(app)
    """
    celery_app.autodiscover_tasks(["ftn_audit"], force=True)

    registered = getattr(celery_app, "tasks", {})
    if TASK_EMIT_AUDIT_LOG not in registered:
        logger.warning(
            "Task '%s' was not registered after autodiscovery. "
            "Ensure workers import the same Celery app instance and keep "
            "ftn_audit task discovery enabled (e.g. configure_celery_audit(app)).",
            TASK_EMIT_AUDIT_LOG,
        )
