"""Django signal receivers for model create / update / delete."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.db.models.signals import post_delete, post_save, pre_save

from ftn_audit.changeset import build_changeset
from ftn_audit.context_storage import get_current_audit_context
from ftn_audit.formatter_factory import AuditLogFormatterFactory
from ftn_audit.registry import AuditFormattersRegistry
from ftn_audit.strategy import get_audit_strategy

logger = logging.getLogger("audit")

# Temporary storage for pre_save changesets (instance id → changeset)
_pending_changesets: Dict[int, Dict[str, Any]] = {}


def _pre_save_receiver(sender, instance, **kwargs):
    """Capture dirty-field changeset *before* the DB write."""
    if not AuditFormattersRegistry.has_model(sender):
        return
    try:
        if instance.pk:
            changeset = build_changeset(instance)
            if changeset:
                _pending_changesets[id(instance)] = changeset
    except Exception:
        logger.debug("pre_save changeset capture failed for %s", sender.__name__, exc_info=True)


def _post_save_receiver(sender, instance, created, **kwargs):
    """Emit creation or update audit event."""
    if not AuditFormattersRegistry.has_model(sender):
        return
    try:
        ctx = get_current_audit_context()
        if ctx is None:
            return

        if created:
            event_type = "creation"
            changeset = None
        else:
            event_type = "update"
            changeset = _pending_changesets.pop(id(instance), None)
            if not changeset:
                return  # nothing changed

        formatter = AuditLogFormatterFactory.make(ctx, instance, event_type, changeset)
        strategy = get_audit_strategy()
        strategy.emit(formatter.get_description(), formatter.get_attributes())
    except Exception:
        logger.exception("post_save audit failed for %s #%s", sender.__name__, getattr(instance, "pk", "?"))
    finally:
        _pending_changesets.pop(id(instance), None)


def _post_delete_receiver(sender, instance, **kwargs):
    """Emit deletion audit event."""
    if not AuditFormattersRegistry.has_model(sender):
        return
    try:
        ctx = get_current_audit_context()
        if ctx is None:
            return
        formatter = AuditLogFormatterFactory.make(ctx, instance, "deletion")
        strategy = get_audit_strategy()
        strategy.emit(formatter.get_description(), formatter.get_attributes())
    except Exception:
        logger.exception("post_delete audit failed for %s #%s", sender.__name__, getattr(instance, "pk", "?"))


def connect_signals():
    """Wire up the signal receivers (called from AppConfig.ready)."""
    pre_save.connect(_pre_save_receiver, dispatch_uid="ftn_audit_pre_save")
    post_save.connect(_post_save_receiver, dispatch_uid="ftn_audit_post_save")
    post_delete.connect(_post_delete_receiver, dispatch_uid="ftn_audit_post_delete")
