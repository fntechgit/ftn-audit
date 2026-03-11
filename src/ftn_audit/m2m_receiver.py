"""M2M signal receiver for auditing many-to-many relation changes."""

from __future__ import annotations

import logging
from typing import Optional, Set

from django.db.models.signals import m2m_changed

from ftn_audit.collections_registry import AuditCollectionsRegistry
from ftn_audit.context import AuditContext
from ftn_audit.context_storage import get_current_audit_context
from ftn_audit.generic_formatters import GenericCollectionUpdateFormatter
from ftn_audit.strategy import get_audit_strategy

logger = logging.getLogger("audit.m2m")


def _m2m_changed_receiver(sender, instance, action, pk_set, model, **kwargs):
    """Handle post_add / post_remove / post_clear on allowlisted M2M fields."""
    if action not in ("post_add", "post_remove", "post_clear"):
        return

    rule = AuditCollectionsRegistry.find_by_through(sender)
    if rule is None:
        return

    # Guard against pk_set=None on post_clear
    if action == "post_clear":
        pk_set = pk_set or set()

    try:
        ctx: Optional[AuditContext] = get_current_audit_context()
        if ctx is None:
            return

        formatter_cls = rule.formatter_cls or GenericCollectionUpdateFormatter
        formatter = formatter_cls(
            context=ctx,
            subject=instance,
            event_type="collection_update",
            field_name=rule.field_name,
            pk_set=pk_set,
            action=action,
        )
        strategy = get_audit_strategy()
        strategy.emit(formatter.get_description(), formatter.get_attributes())
    except Exception:
        logger.exception(
            "m2m audit failed for %s.%s (%s)",
            type(instance).__name__,
            rule.field_name,
            action,
        )


def connect_m2m_signals():
    """Wire up the M2M receiver (called from AppConfig.ready)."""
    m2m_changed.connect(_m2m_changed_receiver, dispatch_uid="ftn_audit_m2m_changed")
