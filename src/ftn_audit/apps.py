"""Django AppConfig for ftn-audit."""

from django.apps import AppConfig


class FtnAuditConfig(AppConfig):
    name = "ftn_audit"
    verbose_name = "FTN Audit Logging"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from ftn_audit.receiver import connect_signals
        from ftn_audit.m2m_receiver import connect_m2m_signals
        from ftn_audit.autodiscover import autodiscover_formatters

        connect_signals()
        connect_m2m_signals()
        autodiscover_formatters()
