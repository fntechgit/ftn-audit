"""Context hydration helpers for audit context."""

from __future__ import annotations

import dataclasses
from typing import Optional

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import (
    get_current_audit_context,
    get_current_audit_request,
)


def hydrate_audit_context_user(ctx: Optional[AuditContext]) -> Optional[AuditContext]:
    """Fill user fields from current request when context has no actor yet."""
    if ctx is None or ctx.user_id is not None:
        return ctx

    request = get_current_audit_request()
    user = getattr(request, "user", None) if request is not None else None
    if not user or not getattr(user, "is_authenticated", False):
        return ctx

    return dataclasses.replace(
        ctx,
        user_id=getattr(user, "pk", None) or getattr(user, "id", None),
        user_email=getattr(user, "email", None),
        user_first_name=getattr(user, "first_name", None),
        user_last_name=getattr(user, "last_name", None),
    )


def get_current_audit_context_with_user() -> Optional[AuditContext]:
    """Get current context with best-effort actor hydration from request."""
    return hydrate_audit_context_user(get_current_audit_context())
