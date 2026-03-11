"""ASGI-safe context storage using contextvars."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from ftn_audit.context import AuditContext

_audit_context_var: ContextVar[Optional[AuditContext]] = ContextVar(
    "ftn_audit_context", default=None
)


def set_current_audit_context(ctx: Optional[AuditContext]) -> None:
    _audit_context_var.set(ctx)


def get_current_audit_context() -> Optional[AuditContext]:
    return _audit_context_var.get()
