"""Factory that resolves the correct formatter for a given audit event."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.conf import settings

from ftn_audit.base_formatter import IAuditLogFormatter
from ftn_audit.constants import (
    DEFAULT_STRICT_FORMATTER_VALIDATION,
    EVENT_CREATION,
    EVENT_DELETION,
    EVENT_UPDATE,
    LOGGER_AUDIT,
    SETTING_AUDIT_STRICT_FORMATTER_VALIDATION,
)
from ftn_audit.context import AuditContext
from ftn_audit.generic_formatters import (
    GenericCreationFormatter,
    GenericDeletionFormatter,
    GenericUpdateFormatter,
)
from ftn_audit.registry import AuditFormattersRegistry

_GENERIC_MAP = {
    EVENT_CREATION: GenericCreationFormatter,
    EVENT_UPDATE: GenericUpdateFormatter,
    EVENT_DELETION: GenericDeletionFormatter,
}

logger = logging.getLogger(LOGGER_AUDIT)


class AuditLogFormatterFactory:
    @staticmethod
    def make(
        ctx: AuditContext,
        subject: Any,
        event_type: str,
        changeset: Optional[Dict[str, Any]] = None,
    ) -> IAuditLogFormatter:
        model = type(subject)
        formatter_cls = AuditFormattersRegistry.find(
            model, raw_route=ctx.raw_route, event_type=event_type
        )
        if formatter_cls is None:
            formatter_cls = _GENERIC_MAP.get(event_type, GenericUpdateFormatter)

        formatter = formatter_cls(
            context=ctx,
            subject=subject,
            event_type=event_type,
            changeset=changeset,
        )
        _validate_formatter_instance(formatter, model, event_type, ctx.raw_route)
        return formatter


def _validate_formatter_instance(
    formatter: object,
    model: type,
    event_type: str,
    raw_route: Optional[str],
) -> None:
    if isinstance(formatter, IAuditLogFormatter):
        return

    message = (
        "Invalid audit formatter instance for "
        f"model={model.__name__} event_type={event_type} route={raw_route!r}. "
        "Expected methods: get_description() and get_attributes()."
    )
    if getattr(
        settings,
        SETTING_AUDIT_STRICT_FORMATTER_VALIDATION,
        DEFAULT_STRICT_FORMATTER_VALIDATION,
    ):
        raise TypeError(message)
    logger.error(message)
