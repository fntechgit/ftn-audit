"""Auto-discover audit_formatters modules from all INSTALLED_APPS."""

from __future__ import annotations

import importlib
import logging

from django.apps import apps

logger = logging.getLogger("audit")


def autodiscover_formatters():
    """Import ``<app_label>.audit_formatters`` for every installed app."""
    for app_config in apps.get_app_configs():
        module_name = f"{app_config.name}.audit_formatters"
        try:
            importlib.import_module(module_name)
            logger.debug("Discovered audit formatters in %s", module_name)
        except ModuleNotFoundError:
            pass
        except Exception:
            logger.warning(
                "Error importing %s", module_name, exc_info=True
            )
