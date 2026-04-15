from __future__ import annotations

from ftn_audit.context_hydration import (
    get_current_audit_context_with_user,
    hydrate_audit_context_user,
)
from ftn_audit.context import AuditContext
from ftn_audit.context_storage import (
    set_current_audit_context,
    set_current_audit_request,
)


class _AuthUser:
    is_authenticated = True
    pk = 123
    email = "actor@example.test"
    first_name = "Actor"
    last_name = "Resolved"


class _AnonymousUser:
    is_authenticated = False


class _RequestWithAuthUser:
    user = _AuthUser()


class _RequestWithAnonymousUser:
    user = _AnonymousUser()


def setup_function():
    set_current_audit_context(None)
    set_current_audit_request(None)


def teardown_function():
    set_current_audit_context(None)
    set_current_audit_request(None)


def test_hydrate_audit_context_user_returns_same_context_when_user_is_already_set():
    ctx = AuditContext(user_id=999, user_email="already@set.test")
    hydrated = hydrate_audit_context_user(ctx)
    assert hydrated is ctx


def test_hydrate_audit_context_user_populates_actor_from_authenticated_request_user():
    ctx = AuditContext(user_id=None, raw_route="PATCH|/v1/items/:id/")
    set_current_audit_request(_RequestWithAuthUser())

    hydrated = hydrate_audit_context_user(ctx)

    assert hydrated is not None
    assert hydrated.user_id == 123
    assert hydrated.user_email == "actor@example.test"
    assert hydrated.user_first_name == "Actor"
    assert hydrated.user_last_name == "Resolved"
    assert hydrated.raw_route == "PATCH|/v1/items/:id/"


def test_get_current_audit_context_with_user_keeps_context_when_request_user_is_anonymous():
    ctx = AuditContext(user_id=None, raw_route="GET|/public/")
    set_current_audit_context(ctx)
    set_current_audit_request(_RequestWithAnonymousUser())

    hydrated = get_current_audit_context_with_user()

    assert hydrated is ctx
    assert hydrated.user_id is None
