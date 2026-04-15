from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from django.test import RequestFactory

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import (
    get_current_audit_context,
    get_current_audit_request,
    set_current_audit_context,
    set_current_audit_request,
)
from ftn_audit.middleware import AuditContextMiddleware


class _AuthUser:
    is_authenticated = True
    pk = 99
    email = "fntech@exomindset.com"
    first_name = "Fntech"
    last_name = "Exomindset"


class _AnonymousUser:
    is_authenticated = False


@pytest.mark.django_db
class TestAuditContextMiddleware:
    def setup_method(self):
        set_current_audit_context(None)
        set_current_audit_request(None)
        self.factory = RequestFactory()

    def teardown_method(self):
        set_current_audit_context(None)
        set_current_audit_request(None)

    def test_process_view_builds_context_for_authenticated_user(self):
        middleware = AuditContextMiddleware(lambda request: None)
        request = self.factory.post(
            "/v1/login/",
            HTTP_X_FORWARDED_FOR="10.0.0.2, 10.0.0.3",
            HTTP_USER_AGENT="pytest-agent",
            HTTP_X_UI_APP="backoffice",
            HTTP_X_UI_FLOW="login",
            HTTP_X_REQUEST_ID="req-123",
        )
        request.user = _AuthUser()
        request.resolver_match = SimpleNamespace(route="v1/login/")

        middleware.process_view(request, lambda req: None, (), {})

        ctx = get_current_audit_context()
        assert ctx is not None
        assert ctx.user_id == 99
        assert ctx.user_email == "fntech@exomindset.com"
        assert ctx.http_method == "POST"
        assert ctx.route == "/v1/login/"
        assert ctx.raw_route == "POST|/v1/login/"
        assert ctx.client_ip == "10.0.0.2"
        assert ctx.user_agent == "pytest-agent"
        assert ctx.ui_app == "backoffice"
        assert ctx.ui_flow == "login"
        assert ctx.request_id == "req-123"

    def test_process_view_keeps_user_fields_empty_for_anonymous(self):
        middleware = AuditContextMiddleware(lambda request: None)
        request = self.factory.get("/public/")
        request.user = _AnonymousUser()
        request.resolver_match = SimpleNamespace(route="public/")

        middleware.process_view(request, lambda req: None, (), {})

        ctx = get_current_audit_context()
        assert ctx is not None
        assert ctx.user_id is None
        assert ctx.user_email is None
        assert ctx.raw_route == "GET|/public/"

    def test_process_view_normalizes_typed_route_params(self):
        middleware = AuditContextMiddleware(lambda request: None)
        request = self.factory.get("/v1/users/42/orders/abc/")
        request.user = _AnonymousUser()
        request.resolver_match = SimpleNamespace(
            route="v1/users/<int:user_id>/orders/<uuid:order_id>/"
        )

        middleware.process_view(request, lambda req: None, (), {})

        ctx = get_current_audit_context()
        assert ctx is not None
        assert ctx.raw_route == "GET|/v1/users/:user_id/orders/:order_id/"

    def test_process_view_normalizes_regex_named_groups_for_drf(self):
        middleware = AuditContextMiddleware(lambda request: None)
        request = self.factory.get("/v1/users/42/")
        request.user = _AnonymousUser()
        request.resolver_match = SimpleNamespace(
            route=r"^v1/users/(?P<user_id>[^/.]+)/$"
        )

        middleware.process_view(request, lambda req: None, (), {})

        ctx = get_current_audit_context()
        assert ctx is not None
        assert ctx.raw_route == "GET|/v1/users/:user_id/"

    def test_call_always_clears_context(self):
        middleware = AuditContextMiddleware(lambda request: (_ for _ in ()).throw(RuntimeError("boom")))
        set_current_audit_context(AuditContext(user_id=5))
        request = self.factory.get("/")

        with pytest.raises(RuntimeError, match="boom"):
            middleware(request)

        assert get_current_audit_context() is None
        assert get_current_audit_request() is None

    def test_async_call_always_clears_context(self):
        async def _boom(_request):
            raise RuntimeError("async boom")

        middleware = AuditContextMiddleware(_boom)

        async def _run_and_assert():
            set_current_audit_context(AuditContext(user_id=5))
            request = self.factory.get("/")
            with pytest.raises(RuntimeError, match="async boom"):
                await middleware(request)
            assert get_current_audit_context() is None
            assert get_current_audit_request() is None

        asyncio.run(_run_and_assert())
