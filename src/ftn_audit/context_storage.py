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


_AuditScopeTokens = Tuple[Token[Optional[AuditContext]], Token[Optional[HttpRequest]]]

# Tokens of the scopes entered in the current context, innermost last. Kept in a
# ContextVar rather than on the scope object: a token can only be reset in the
# context that created it, and one scope object may be entered from several
# tasks or threads at once, or re-entered while it is still active.
_audit_scope_stack_var: ContextVar[Tuple[_AuditScopeTokens, ...]] = ContextVar(
    "ftn_audit_scope_stack", default=()
)


def enter_audit_scope(ctx: AuditContext) -> None:
    """Make ``ctx`` current with no request, remembering the previous state."""
    tokens = (_audit_context_var.set(ctx), _audit_request_var.set(None))
    _audit_scope_stack_var.set(_audit_scope_stack_var.get() + (tokens,))


def exit_audit_scope() -> None:
    """Restore the context and request that were current before the innermost ``enter_audit_scope``."""
    stack = _audit_scope_stack_var.get()
    if not stack:
        raise RuntimeError("exit_audit_scope() called without a matching enter_audit_scope()")
    context_token, request_token = stack[-1]
    _audit_scope_stack_var.set(stack[:-1])
    _audit_request_var.reset(request_token)
    _audit_context_var.reset(context_token)
