"""Factory that resolves the correct formatter for a given audit event."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ftn_audit.base_formatter import IAuditLogFormatter
from ftn_audit.context import AuditContext
from ftn_audit.generic_formatters import (
    GenericCreationFormatter,
    GenericDeletionFormatter,
    GenericUpdateFormatter,
)
from ftn_audit.registry import AuditFormattersRegistry

_GENERIC_MAP = {
    "creation": GenericCreationFormatter,
    "update": GenericUpdateFormatter,
    "deletion": GenericDeletionFormatter,
}


class AuditLogFormatterFactory:
    @staticmethod
    def make(
        ctx: AuditContext,
        subject: Any,
        event_type: str,
        changeset: Optional[Dict[str, Any]] = None,
    ) -> IAuditLogFormatter:
        model = type(subject)
        # 1. Registry lookup (route → model default → None)
        formatter_cls = AuditFormattersRegistry.find(
            model, raw_route=ctx.raw_route, event_type=event_type
        )
        # 2. Generic fallback
        if formatter_cls is None:
            formatter_cls = _GENERIC_MAP.get(event_type, GenericUpdateFormatter)

        return formatter_cls(
            context=ctx,
            subject=subject,
            event_type=event_type,
            changeset=changeset,
        )
