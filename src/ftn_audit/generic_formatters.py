"""Generic formatters used as fallbacks when no custom formatter is registered."""

from __future__ import annotations

from typing import Any, Dict

from ftn_audit.base_formatter import AbstractAuditLogFormatter


class GenericCreationFormatter(AbstractAuditLogFormatter):
    def get_description(self) -> str:
        model_name = type(self.subject).__name__
        return f"Created {model_name} #{self.subject.pk}"

    def get_attributes(self) -> Dict[str, Any]:
        return {
            "audit.event_type": self.event_type,
            "audit.model": type(self.subject).__name__,
            "audit.model_pk": str(self.subject.pk),
            **self.get_user_info(),
        }


class GenericUpdateFormatter(AbstractAuditLogFormatter):
    def get_description(self) -> str:
        model_name = type(self.subject).__name__
        changes = self.build_change_details()
        fields = ", ".join(changes.keys()) if changes else "no fields"
        return f"Updated {model_name} #{self.subject.pk} ({fields})"

    def get_attributes(self) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {
            "audit.event_type": self.event_type,
            "audit.model": type(self.subject).__name__,
            "audit.model_pk": str(self.subject.pk),
            **self.get_user_info(),
        }
        changes = self.build_change_details()
        if changes:
            attrs["audit.changeset"] = changes
        return attrs


class GenericDeletionFormatter(AbstractAuditLogFormatter):
    def get_description(self) -> str:
        model_name = type(self.subject).__name__
        return f"Deleted {model_name} #{self.subject.pk}"

    def get_attributes(self) -> Dict[str, Any]:
        return {
            "audit.event_type": self.event_type,
            "audit.model": type(self.subject).__name__,
            "audit.model_pk": str(self.subject.pk),
            **self.get_user_info(),
        }


class GenericCollectionUpdateFormatter(AbstractAuditLogFormatter):
    """Handles M2M add/remove/clear events."""

    def __init__(self, context, subject, event_type, *, field_name: str, pk_set=None, action: str = "", **kwargs):
        super().__init__(context, subject, event_type)
        self.field_name = field_name
        self.pk_set = pk_set
        self.action = action

    def get_description(self) -> str:
        model_name = type(self.subject).__name__
        return f"{self.action} on {model_name} #{self.subject.pk}.{self.field_name}"

    def get_attributes(self) -> Dict[str, Any]:
        return {
            "audit.event_type": self.event_type,
            "audit.model": type(self.subject).__name__,
            "audit.model_pk": str(self.subject.pk),
            "audit.field_name": self.field_name,
            "audit.action": self.action,
            "audit.pk_set": sorted(self.pk_set) if self.pk_set else [],
            **self.get_user_info(),
        }
