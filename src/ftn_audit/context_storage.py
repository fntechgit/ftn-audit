"""ASGI-safe context storage using contextvars."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional, Tuple

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


AuditScopeTokens = Tuple[Token[Optional[AuditContext]], Token[Optional[HttpRequest]]]


def enter_audit_scope(ctx: AuditContext) -> AuditScopeTokens:
    """Make ``ctx`` current with no request; return the tokens to undo it."""
    return _audit_context_var.set(ctx), _audit_request_var.set(None)


def exit_audit_scope(tokens: AuditScopeTokens) -> None:
    """Restore the context and request that were current before ``enter_audit_scope``."""
    context_token, request_token = tokens
    _audit_request_var.reset(request_token)
    _audit_context_var.reset(context_token)
