"""Build a changeset dict from a DirtyFieldsMixin-enabled model instance."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ftn_audit.serialization import make_json_safe

logger = logging.getLogger("audit")


def build_changeset(instance) -> Optional[Dict[str, Any]]:
    """Return ``{field: {old, new}}`` for dirty fields, or *None*."""
    get_dirty = getattr(instance, "get_dirty_fields", None)
    if get_dirty is None:
        return None
    try:
        dirty = get_dirty(check_relationship=True)
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
