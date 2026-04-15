"""M2M signal receiver for auditing many-to-many relation changes."""

from __future__ import annotations

import logging
from itertools import islice
from typing import Set

from django.db.models.signals import m2m_changed

from ftn_audit.context_hydration import get_current_audit_context_with_user
from ftn_audit.collections_registry import AuditCollectionsRegistry
from ftn_audit.constants import (
    DISPATCH_UID_M2M_CHANGED,
    EVENT_COLLECTION_UPDATE,
    LOGGER_AUDIT_M2M,
    M2M_PK_SET_MAX,
    M2M_ACTION_POST_CLEAR,
    M2M_ACTION_PRE_CLEAR,
    M2M_TRACKED_ACTIONS,
)
from ftn_audit.formatter_emitter import FormatterEmitter
from ftn_audit.generic_formatters import GenericCollectionUpdateFormatter

logger = logging.getLogger(LOGGER_AUDIT_M2M)
_EMITTER = FormatterEmitter(logger=logger)
_PRE_CLEAR_ATTR = "_ftn_audit_pre_clear_pk_sets"


def _cache_pre_clear_pk_set(instance, field_name: str) -> None:
    cached = getattr(instance, _PRE_CLEAR_ATTR, None)
    if cached is None:
        cached = {}
        setattr(instance, _PRE_CLEAR_ATTR, cached)

    related_manager = getattr(instance, field_name)
    cached[field_name] = set(related_manager.values_list("pk", flat=True)[:M2M_PK_SET_MAX])


def _cap_pk_set(pk_set) -> Set[int]:
    if not pk_set:
        return set()
    return set(islice(pk_set, M2M_PK_SET_MAX))


def _pop_pre_clear_pk_set(instance, field_name: str) -> Set[int]:
    cached = getattr(instance, _PRE_CLEAR_ATTR, None)
    if not cached:
        return set()

    pk_set = cached.pop(field_name, set())
    if not cached:
        try:
            delattr(instance, _PRE_CLEAR_ATTR)
        except Exception:
            logger.debug("failed cleaning pre_clear cache for %s.%s", type(instance).__name__, field_name, exc_info=True)
    return _cap_pk_set(pk_set)


def _m2m_changed_receiver(sender, instance, action, pk_set, model, reverse=False, **kwargs):
    """Handle post_add / post_remove / post_clear on allowlisted M2M fields."""
    if action not in M2M_TRACKED_ACTIONS:
        return

    rule = AuditCollectionsRegistry.find_by_through(sender)
    if rule is None:
        return
    if reverse:
        return
    if not isinstance(instance, rule.owner_model):
        return

    if action == M2M_ACTION_PRE_CLEAR:
        try:
            _cache_pre_clear_pk_set(instance, rule.field_name)
        except Exception:
            logger.exception(
                "m2m pre_clear snapshot failed for %s.%s",
                type(instance).__name__,
                rule.field_name,
            )
        return

    if action == M2M_ACTION_POST_CLEAR:
        pk_set = _pop_pre_clear_pk_set(instance, rule.field_name)
    else:
        pk_set = _cap_pk_set(pk_set)

    try:
        ctx = get_current_audit_context_with_user()
        if ctx is None:
            logger.debug(
                "dropping m2m audit event due to missing context for %s.%s (%s)",
                type(instance).__name__,
                rule.field_name,
                action,
            )
            return

        formatter_cls = rule.formatter_cls or GenericCollectionUpdateFormatter
        _EMITTER.emit(
            lambda: formatter_cls(
                context=ctx,
                subject=instance,
                event_type=EVENT_COLLECTION_UPDATE,
                field_name=rule.field_name,
                pk_set=pk_set,
                action=action,
            ),
            not_implemented_message=(
                "Collection formatter for %s.%s raised NotImplementedError. "
                "Use `get_default_attributes()` in your formatter."
            ),
            not_implemented_args=(type(instance).__name__, rule.field_name),
            failure_message="m2m audit failed for %s.%s (%s)",
            failure_args=(type(instance).__name__, rule.field_name, action),
        )
    except Exception:
        logger.exception("m2m audit preconditions failed for %s.%s (%s)", type(instance).__name__, rule.field_name, action)


def connect_m2m_signals():
    """Wire up the M2M receiver."""
    m2m_changed.connect(_m2m_changed_receiver, dispatch_uid=DISPATCH_UID_M2M_CHANGED)
    logger.debug("ftn_audit m2m signal connected")
