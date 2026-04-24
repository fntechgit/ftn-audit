"""Context hydration helpers for audit context."""

from __future__ import annotations

import dataclasses
from typing import Optional

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import (
    get_current_audit_context,
    get_current_audit_request,
)


def _hydrate_from_request_auth(
    ctx: AuditContext,
    request,
) -> Optional[AuditContext]:
    token_info = getattr(request, "auth", None)
    if not isinstance(token_info, dict):
        return None

    user_id = token_info.get("user_id")
    if user_id is not None:
        try:
            user_id = int(user_id)
        except Exception:
            user_id = None

    user_email = token_info.get("user_email")
    user_first_name = token_info.get("user_first_name")
    user_last_name = token_info.get("user_last_name")

    if (
        user_id is None
        and not user_email
        and not user_first_name
        and not user_last_name
    ):
        return None

    return dataclasses.replace(
        ctx,
        user_id=user_id,
        user_email=user_email,
        user_first_name=user_first_name,
        user_last_name=user_last_name,
    )


def hydrate_audit_context_user(ctx: Optional[AuditContext]) -> Optional[AuditContext]:
    """Fill user fields from current request when context has no actor yet."""
    if ctx is None or ctx.user_id is not None:
        return ctx

    request = get_current_audit_request()
    if request is None:
        return ctx

    hydrated_from_auth = _hydrate_from_request_auth(ctx, request)
    if hydrated_from_auth is not None:
        return hydrated_from_auth

    user = getattr(request, "user", None)
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
