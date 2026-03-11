"""Audit context middleware — extracts user/request info for every request."""

from __future__ import annotations

import logging
import uuid
from typing import Callable, Optional

from django.http import HttpRequest, HttpResponse

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import set_current_audit_context

logger = logging.getLogger("audit")


class AuditContextMiddleware:
    """Populates an ``AuditContext`` from every incoming request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.get_response(request)
        finally:
            set_current_audit_context(None)

    # noinspection PyMethodMayBeStatic
    def process_view(self, request: HttpRequest, view_func, view_args, view_kwargs):
        """Called after URL resolution — ``resolver_match`` is available."""
        try:
            user = getattr(request, "user", None)
            user_id: Optional[int] = None
            user_email: Optional[str] = None
            user_first_name: Optional[str] = None
            user_last_name: Optional[str] = None

            if user and getattr(user, "is_authenticated", False):
                user_id = getattr(user, "pk", None) or getattr(user, "id", None)
                user_email = getattr(user, "email", None)
                user_first_name = getattr(user, "first_name", None)
                user_last_name = getattr(user, "last_name", None)

            raw_route = self._build_raw_route(request)

            ctx = AuditContext(
                user_id=user_id,
                user_email=user_email,
                user_first_name=user_first_name,
                user_last_name=user_last_name,
                http_method=request.method,
                route=request.path,
                raw_route=raw_route,
                client_ip=self._get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                ui_app=request.META.get("HTTP_X_UI_APP", ""),
                ui_flow=request.META.get("HTTP_X_UI_FLOW", ""),
                request_id=request.META.get(
                    "HTTP_X_REQUEST_ID", str(uuid.uuid4())
                ),
                trace_id=self._get_trace_id(),
            )
            set_current_audit_context(ctx)
        except Exception:
            logger.exception("Failed to build AuditContext")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_raw_route(request: HttpRequest) -> Optional[str]:
        match = getattr(request, "resolver_match", None)
        if match is None:
            return None
        pattern = getattr(match, "route", None) or request.path
        return f"{request.method}|/{pattern.lstrip('/')}"

    @staticmethod
    def _get_client_ip(request: HttpRequest) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    @staticmethod
    def _get_trace_id() -> Optional[str]:
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.trace_id:
                return format(ctx.trace_id, "032x")
        except Exception:
            pass
        return None
