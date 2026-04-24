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

AUTH_USER_ID = 123
AUTH_USER_EMAIL = "actor@fntech.com.ar"
AUTH_USER_FIRST_NAME = "Juan"
AUTH_USER_LAST_NAME = "Pérez"

ALREADY_SET_EMAIL = "ya@seteado.com.ar"

AUTH_TOKEN_USER_ID_STR = "321"
AUTH_TOKEN_EMAIL = "oauth@fntech.com.ar"
AUTH_TOKEN_FIRST_NAME = "Lucía"
AUTH_TOKEN_LAST_NAME = "Gómez"

TOKEN_USER_ID = 456
TOKEN_USER_EMAIL = "token@fntech.com.ar"


class _AuthUser:
    is_authenticated = True
    pk = AUTH_USER_ID
    email = AUTH_USER_EMAIL
    first_name = AUTH_USER_FIRST_NAME
    last_name = AUTH_USER_LAST_NAME


class _AnonymousUser:
    is_authenticated = False


class _RequestWithAuthToken:
    def __init__(self, auth, user=None):
        self.auth = auth
        self.user = user if user is not None else _AnonymousUser()


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
    ctx = AuditContext(user_id=999, user_email=ALREADY_SET_EMAIL)
    hydrated = hydrate_audit_context_user(ctx)
    assert hydrated is ctx


def test_hydrate_audit_context_user_populates_actor_from_request_auth_token_fields():
    ctx = AuditContext(user_id=None, raw_route="PATCH|/v1/items/:id/")
    set_current_audit_request(
        _RequestWithAuthToken(
            {
                "user_id": AUTH_TOKEN_USER_ID_STR,
                "user_email": AUTH_TOKEN_EMAIL,
                "user_first_name": AUTH_TOKEN_FIRST_NAME,
                "user_last_name": AUTH_TOKEN_LAST_NAME,
            }
        )
    )

    hydrated = hydrate_audit_context_user(ctx)

    assert hydrated is not None
    assert hydrated.user_id == 321
    assert hydrated.user_email == AUTH_TOKEN_EMAIL
    assert hydrated.user_first_name == AUTH_TOKEN_FIRST_NAME
    assert hydrated.user_last_name == AUTH_TOKEN_LAST_NAME
    assert hydrated.raw_route == "PATCH|/v1/items/:id/"


def test_hydrate_audit_context_user_prefers_request_auth_over_request_user_fallback():
    ctx = AuditContext(user_id=None)
    set_current_audit_request(
        _RequestWithAuthToken(
            {"user_id": TOKEN_USER_ID, "user_email": TOKEN_USER_EMAIL},
            user=_AuthUser(),
        )
    )

    hydrated = hydrate_audit_context_user(ctx)

    assert hydrated is not None
    assert hydrated.user_id == TOKEN_USER_ID
    assert hydrated.user_email == TOKEN_USER_EMAIL
    assert hydrated.user_first_name is None
    assert hydrated.user_last_name is None


def test_hydrate_audit_context_user_falls_back_to_request_user_when_auth_is_not_dict():
    ctx = AuditContext(user_id=None)
    request = _RequestWithAuthUser()
    request.auth = "not-a-dict"
    set_current_audit_request(request)

    hydrated = hydrate_audit_context_user(ctx)

    assert hydrated is not None
    assert hydrated.user_id == AUTH_USER_ID
    assert hydrated.user_email == AUTH_USER_EMAIL
    assert hydrated.user_first_name == AUTH_USER_FIRST_NAME
    assert hydrated.user_last_name == AUTH_USER_LAST_NAME


def test_get_current_audit_context_with_user_keeps_context_when_request_is_anonymous_and_has_no_auth_data():
    ctx = AuditContext(user_id=None, raw_route="GET|/public/")
    set_current_audit_context(ctx)
    set_current_audit_request(_RequestWithAnonymousUser())

    hydrated = get_current_audit_context_with_user()

    assert hydrated is ctx
    assert hydrated.user_id is None
