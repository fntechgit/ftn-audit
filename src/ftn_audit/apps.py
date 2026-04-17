"""Django AppConfig for ftn-audit."""

import logging

from django.apps import AppConfig
from django.conf import settings

from ftn_audit.constants import (
    DEFAULT_AUTO_CONNECT_SIGNALS,
    DEFAULT_AUTO_DISCOVER_FORMATTERS,
    LOGGER_AUDIT,
    SETTING_AUDIT_AUTO_CONNECT_SIGNALS,
    SETTING_AUDIT_AUTO_DISCOVER_FORMATTERS,
)

logger = logging.getLogger(LOGGER_AUDIT)


class FtnAuditConfig(AppConfig):
    name = "ftn_audit"
    verbose_name = "FTN Audit Logging"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from ftn_audit.receiver import connect_signals
        from ftn_audit.m2m_receiver import connect_m2m_signals
        from ftn_audit.autodiscover import autodiscover_formatters

        if getattr(
            settings,
            SETTING_AUDIT_AUTO_CONNECT_SIGNALS,
            DEFAULT_AUTO_CONNECT_SIGNALS,
        ):
            connect_signals()
            connect_m2m_signals()
        if getattr(
            settings,
            SETTING_AUDIT_AUTO_DISCOVER_FORMATTERS,
            DEFAULT_AUTO_DISCOVER_FORMATTERS,
        ):
            autodiscover_formatters()
        logger.debug("ftn_audit AppConfig ready completed")
