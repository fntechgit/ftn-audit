"""Auto-discover audit_formatters modules from all INSTALLED_APPS."""

from __future__ import annotations

import importlib
import logging

from django.apps import apps

from ftn_audit.constants import LOGGER_AUDIT, TASK_EMIT_AUDIT_LOG

logger = logging.getLogger(LOGGER_AUDIT)


def autodiscover_formatters():
    """Import ``<app_label>.audit_formatters`` for every installed app."""
    for app_config in apps.get_app_configs():
        module_name = f"{app_config.name}.audit_formatters"
        try:
            importlib.import_module(module_name)
            logger.debug("Discovered audit formatters in %s", module_name)
        except ModuleNotFoundError as exc:
            if exc.name == module_name:
                continue
            logger.warning(
                "Error importing %s. Check nested imports inside that module.",
                module_name,
                exc_info=True,
            )
        except Exception:
            logger.warning(
                "Error importing %s. Your custom formatter registration may be incomplete.",
                module_name,
                exc_info=True,
            )


def verify_celery_task_registered() -> None:
    """Log integration hints when the shared Celery task is not visible."""
    try:
        from celery import current_app
    except Exception:
        logger.debug("Celery not importable while checking task registration.")
        return

    if TASK_EMIT_AUDIT_LOG not in getattr(current_app, "tasks", {}):
        logger.warning(
            "Task '%s' not registered in current Celery app. "
            "Enable ftn_audit task discovery in your Celery setup "
            "(e.g. ftn_audit.configure_celery_audit(app)).",
            TASK_EMIT_AUDIT_LOG,
        )
