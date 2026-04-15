"""Django signal receivers for model create / update / delete."""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save, pre_save

from ftn_audit.context_hydration import get_current_audit_context_with_user
from ftn_audit.changeset import build_changeset
from ftn_audit.constants import (
    DISPATCH_UID_POST_DELETE,
    DISPATCH_UID_POST_SAVE,
    DISPATCH_UID_PRE_SAVE,
    EVENT_CREATION,
    EVENT_DELETION,
    EVENT_UPDATE,
    LOGGER_AUDIT,
)
from ftn_audit.formatter_factory import AuditLogFormatterFactory
from ftn_audit.formatter_emitter import FormatterEmitter
from ftn_audit.registry import AuditFormattersRegistry

logger = logging.getLogger(LOGGER_AUDIT)

_CHANGESET_ATTR = "_ftn_audit_pending_changeset"
_EMITTER = FormatterEmitter(logger=logger)


def _pre_save_receiver(sender, instance, **kwargs):
    """Capture dirty-field changeset *before* the DB write."""
    if kwargs.get("raw"):
        return
    if not AuditFormattersRegistry.has_model(sender):
        return
    try:
        if instance.pk:
            changeset = build_changeset(instance)
            changeset = _filter_changeset_by_update_fields(
                instance,
                changeset,
                kwargs.get("update_fields"),
            )
            if changeset:
                setattr(instance, _CHANGESET_ATTR, changeset)
    except Exception:
        logger.debug("pre_save changeset capture failed for %s", sender.__name__, exc_info=True)


def _post_save_receiver(sender, instance, created, **kwargs):
    """Emit creation or update audit event."""
    if kwargs.get("raw"):
        return
    if not AuditFormattersRegistry.has_model(sender):
        return
    try:
        ctx = get_current_audit_context_with_user()
        if ctx is None:
            logger.debug(
                "dropping post_save audit event due to missing context for %s #%s",
                sender.__name__,
                getattr(instance, "pk", "?"),
            )
            return

        if created:
            event_type = EVENT_CREATION
            changeset = None
        else:
            event_type = EVENT_UPDATE
            changeset = getattr(instance, _CHANGESET_ATTR, None)
            if not changeset:
                return

        _EMITTER.emit(
            lambda: AuditLogFormatterFactory.make(ctx, instance, event_type, changeset),
            not_implemented_message=(
                "Formatter for %s raised NotImplementedError. "
                "If you use `super().get_attributes()`, inherit from "
                "`AbstractAuditLogFormatter` and use `get_default_attributes()`."
            ),
            not_implemented_args=(sender.__name__,),
            failure_message="post_save audit failed for %s #%s",
            failure_args=(sender.__name__, getattr(instance, "pk", "?")),
        )
    except Exception:
        logger.exception("post_save audit preconditions failed for %s #%s", sender.__name__, getattr(instance, "pk", "?"))
    finally:
        if hasattr(instance, _CHANGESET_ATTR):
            try:
                delattr(instance, _CHANGESET_ATTR)
            except Exception:
                logger.debug(
                    "failed cleaning pending changeset attr for %s",
                    sender.__name__,
                    exc_info=True,
                )


def _filter_changeset_by_update_fields(instance, changeset, update_fields):
    if not changeset or not update_fields:
        return changeset

    allowed = set(update_fields)
    try:
        model_fields = getattr(instance, "_meta", None).fields or []
    except Exception:
        model_fields = []

    for field in model_fields:
        field_name = getattr(field, "name", None)
        attname = getattr(field, "attname", None)
        if field_name in allowed or attname in allowed:
            if field_name:
                allowed.add(field_name)
            if attname:
                allowed.add(attname)

    return {key: value for key, value in changeset.items() if key in allowed}


def _post_delete_receiver(sender, instance, **kwargs):
    """Emit deletion audit event."""
    if not AuditFormattersRegistry.has_model(sender):
        return
    try:
        ctx = get_current_audit_context_with_user()
        if ctx is None:
            logger.debug(
                "dropping post_delete audit event due to missing context for %s #%s",
                sender.__name__,
                getattr(instance, "pk", "?"),
            )
            return
        _EMITTER.emit(
            lambda: AuditLogFormatterFactory.make(ctx, instance, EVENT_DELETION),
            not_implemented_message=(
                "Formatter for %s raised NotImplementedError. "
                "Use `get_default_attributes()` in your custom formatter."
            ),
            not_implemented_args=(sender.__name__,),
            failure_message="post_delete audit failed for %s #%s",
            failure_args=(sender.__name__, getattr(instance, "pk", "?")),
        )
    except Exception:
        logger.exception("post_delete audit preconditions failed for %s #%s", sender.__name__, getattr(instance, "pk", "?"))


def connect_signals():
    """Wire up the signal receivers."""
    pre_save.connect(_pre_save_receiver, dispatch_uid=DISPATCH_UID_PRE_SAVE)
    post_save.connect(_post_save_receiver, dispatch_uid=DISPATCH_UID_POST_SAVE)
    post_delete.connect(_post_delete_receiver, dispatch_uid=DISPATCH_UID_POST_DELETE)
    logger.debug("ftn_audit model signals connected")
