"""ASGI-safe context storage using contextvars."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from django.http import HttpRequest

from ftn_audit.context import AuditContext

_audit_context_var: ContextVar[Optional[AuditContext]] = ContextVar(
    "ftn_audit_context", default=None
)
_audit_request_var: ContextVar[Optional[HttpRequest]] = ContextVar(
    "ftn_audit_request", default=None
)


def set_current_audit_context(ctx: Optional[AuditContext]) -> None:
    _audit_context_var.set(ctx)


def get_current_audit_context() -> Optional[AuditContext]:
    return _audit_context_var.get()


def set_current_audit_request(request: Optional[HttpRequest]) -> None:
    _audit_request_var.set(request)


def get_current_audit_request() -> Optional[HttpRequest]:
    return _audit_request_var.get()
