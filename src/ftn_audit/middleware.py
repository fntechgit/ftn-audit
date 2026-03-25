"""Audit context middleware — extracts user/request info for every request."""

from __future__ import annotations

import logging
import uuid
from typing import Awaitable, Callable, Optional, Union

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import set_current_audit_context

logger = logging.getLogger("audit")


class AuditContextMiddleware:
    """Populates an ``AuditContext`` from every incoming request."""

    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: Union[
            Callable[[HttpRequest], HttpResponse],
            Callable[[HttpRequest], Awaitable[HttpResponse]],
        ],
    ) -> None:
        self.get_response = get_response
        self._is_async = iscoroutinefunction(get_response)
        if self._is_async:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest):
        if self._is_async:
            return self.__acall__(request)
        try:
            return self.get_response(request)
        finally:
            set_current_audit_context(None)

    async def __acall__(self, request: HttpRequest) -> HttpResponse:
        try:
            return await self.get_response(request)
        finally:
            set_current_audit_context(None)

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

    @staticmethod
    def _build_raw_route(request: HttpRequest) -> Optional[str]:
        match = getattr(request, "resolver_match", None)
        if match is None:
            return None
        pattern = getattr(match, "route", None) or request.path
        canonical_pattern = AuditContextMiddleware._canonicalize_route_pattern(pattern)
        return f"{request.method}|/{canonical_pattern.lstrip('/')}"

    @staticmethod
    def _canonicalize_route_pattern(pattern: str) -> str:
        pattern = pattern.lstrip("^").rstrip("$")
        pattern = AuditContextMiddleware._replace_regex_named_groups(pattern)
        canonical_segments = []
        for segment in pattern.split("/"):
            canonical_segments.append(
                AuditContextMiddleware._canonicalize_route_segment(segment)
            )
        return "/".join(canonical_segments)

    @staticmethod
    def _replace_regex_named_groups(pattern: str) -> str:
        rewritten = ""
        cursor = 0
        while True:
            start = pattern.find("(?P<", cursor)
            if start == -1:
                rewritten += pattern[cursor:]
                break

            rewritten += pattern[cursor:start]
            name_end = pattern.find(">", start + 4)
            if name_end == -1:
                rewritten += pattern[start:]
                break

            group_close = pattern.find(")", name_end + 1)
            if group_close == -1:
                rewritten += pattern[start:]
                break

            group_name = pattern[start + 4 : name_end]
            rewritten += f":{group_name}" if group_name else ""
            cursor = group_close + 1

        return rewritten

    @staticmethod
    def _canonicalize_route_segment(segment: str) -> str:
        if segment.startswith("<") and segment.endswith(">"):
            token = segment.replace("<", "").replace(">", "")
            token = token.split(":", 1)[1] if ":" in token else token
            return f":{token}"
        return segment

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
