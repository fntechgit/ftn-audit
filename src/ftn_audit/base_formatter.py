"""Protocol and abstract base for audit log formatters."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from ftn_audit.constants import (
    ATTR_CHANGESET,
    ATTR_EVENT_TYPE,
    ATTR_MODEL,
    ATTR_MODEL_PK,
    ATTR_RAW_ROUTE,
    DEFAULT_IGNORED_CHANGE_FIELDS,
)
from ftn_audit.context import AuditContext


@runtime_checkable
class IAuditLogFormatter(Protocol):
    """Minimal contract every formatter must satisfy."""

    def get_description(self) -> str: ...
    def get_attributes(self) -> Dict[str, Any]: ...


class AbstractAuditLogFormatter:
    """Convenient base class with shared helpers."""

    IGNORED_FIELDS = frozenset(DEFAULT_IGNORED_CHANGE_FIELDS)

    def __init__(
        self,
        context: AuditContext,
        subject: Any,
        event_type: str,
        changeset: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.context = context
        self.subject = subject
        self.event_type = event_type
        self.changeset = changeset

    def get_user_info(self) -> Dict[str, Any]:
        return {
            "user_id": self.context.user_id,
            "user_email": self.context.user_email,
            "user_first_name": self.context.user_first_name,
            "user_last_name": self.context.user_last_name,
        }

    def build_change_details(self) -> Optional[Dict[str, Any]]:
        if not self.changeset:
            return None
        filtered = {
            k: v for k, v in self.changeset.items()
            if k not in self.IGNORED_FIELDS
        }
        return filtered or None

    def get_description(self) -> str:
        raise NotImplementedError

    def get_attributes(self) -> Dict[str, Any]:
        return self.get_default_attributes()

    def get_default_attributes(self) -> Dict[str, Any]:
        """Reusable baseline attributes for most audit events."""
        attrs: Dict[str, Any] = {
            ATTR_EVENT_TYPE: self.event_type,
            ATTR_MODEL: type(self.subject).__name__,
            ATTR_MODEL_PK: str(getattr(self.subject, "pk", "")),
            ATTR_RAW_ROUTE: self.context.raw_route,
            **self.get_user_info(),
        }
        changes = self.build_change_details()
        if changes:
            attrs[ATTR_CHANGESET] = changes
        return attrs

    def merge_attributes(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Convenience helper for subclasses to extend defaults safely."""
        merged = self.get_default_attributes()
        if extra:
            merged.update(extra)
        return merged
