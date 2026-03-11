"""Protocol and abstract base for audit log formatters."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from ftn_audit.context import AuditContext


@runtime_checkable
class IAuditLogFormatter(Protocol):
    """Minimal contract every formatter must satisfy."""

    def get_description(self) -> str: ...
    def get_attributes(self) -> Dict[str, Any]: ...


class AbstractAuditLogFormatter:
    """Convenient base class with shared helpers."""

    IGNORED_FIELDS = frozenset({
        "created", "modified", "created_at", "updated_at",
        "created_by", "updated_by",
    })

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
        raise NotImplementedError
