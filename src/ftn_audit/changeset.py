"""Build a changeset dict from a DirtyFieldsMixin-enabled model instance."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.conf import settings

from ftn_audit.constants import (
    DEFAULT_CHANGESET_CHECK_RELATIONSHIP,
    SETTING_AUDIT_CHANGESET_CHECK_RELATIONSHIP,
)
from ftn_audit.serialization import make_json_safe

logger = logging.getLogger("audit")


def build_changeset(instance, *, check_relationship: Optional[bool] = None) -> Optional[Dict[str, Any]]:
    """Return ``{field: {old, new}}`` for dirty fields, or *None*."""
    get_dirty = getattr(instance, "get_dirty_fields", None)
    if get_dirty is None:
        return None
    should_check_relationship = (
        check_relationship
        if check_relationship is not None
        else getattr(
            settings,
            SETTING_AUDIT_CHANGESET_CHECK_RELATIONSHIP,
            DEFAULT_CHANGESET_CHECK_RELATIONSHIP,
        )
    )
    try:
        dirty = get_dirty(check_relationship=should_check_relationship)
    except Exception:
        logger.debug("get_dirty_fields failed on %s", type(instance).__name__, exc_info=True)
        return None
    if not dirty:
        return None
    changeset: Dict[str, Any] = {}
    for field_name, old_value in dirty.items():
        new_value = getattr(instance, field_name, None)
        changeset[field_name] = {
            "old": make_json_safe(old_value),
            "new": make_json_safe(new_value),
        }
    return changeset
