"""Explicit audit context for code that runs outside an HTTP request.

``AuditContextMiddleware`` only covers requests, and receivers drop every event
that has no context. Scheduled jobs, Celery tasks and message consumers wrap
their work in one of these helpers so their writes are audited too.
"""

from __future__ import annotations

import dataclasses
import functools
import inspect
import uuid
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from ftn_audit.constants import SYSTEM_RAW_ROUTE_METHOD
from ftn_audit.context import AuditContext
from ftn_audit.context_hydration import get_current_audit_context_with_user
from ftn_audit.context_storage import AuditScopeTokens, enter_audit_scope, exit_audit_scope

F = TypeVar("F", bound=Callable[..., Any])


class AuditScope:
    """Context manager and decorator that makes an ``AuditContext`` current.

    The context is built on every entry, so a decorated function gets a fresh
    one per call. Decorated coroutine functions keep the scope across ``await``
    (a plain ``ContextDecorator`` would close it before the body runs).
    """

    def __init__(self, make_context: Callable[[], AuditContext]) -> None:
        self._make_context = make_context
        self._tokens: Optional[AuditScopeTokens] = None

    def __enter__(self) -> AuditContext:
        context = self._make_context()
        self._tokens = enter_audit_scope(context)
        return context

    def __exit__(self, *exc_info: Any) -> None:
        if self._tokens is not None:
            exit_audit_scope(self._tokens)
            self._tokens = None

    def __call__(self, func: F) -> F:
        make_context = self._make_context

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with AuditScope(make_context):
                    return await func(*args, **kwargs)

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with AuditScope(make_context):
                return func(*args, **kwargs)

        return cast(F, wrapper)


def audit_context(context: AuditContext) -> AuditScope:
    """Run the block (or decorated function) under ``context``, then restore the previous one.

    The current request is hidden for the duration, so actor hydration cannot
    attribute these writes to an unrelated request's user.
    """
    return AuditScope(lambda: context)


def system_audit_context(
    source: str,
    *,
    trace_id: Optional[str] = None,
    ui_app: Optional[str] = None,
    ui_flow: Optional[str] = None,
) -> AuditScope:
    """Run the block (or decorated function) as the system actor ``source``.

    ``source`` names the job, task or consumer (e.g. ``"job:reopen_carts"``).
    Events carry ``raw_route = "SYSTEM|<source>"``, which identifies it in the
    audit trail and lets formatters register for it like any route, and a fresh
    ``request_id`` per entry. Only request metadata can be added: code acting
    on behalf of a user should use ``audit_context()`` with that user instead.
    """
    raw_route = f"{SYSTEM_RAW_ROUTE_METHOD}|{source}"
    return AuditScope(lambda: AuditContext(
        route=source,
        raw_route=raw_route,
        request_id=str(uuid.uuid4()),
        trace_id=trace_id,
        ui_app=ui_app,
        ui_flow=ui_flow,
    ))


def snapshot_current_audit_context() -> Optional[Dict[str, Any]]:
    """Serializable copy of the current context, actor included, or None.

    Pass it to a Celery task and restore it there with
    ``audit_context(audit_context_from_snapshot(snapshot))`` so the task's
    writes are attributed to the user who triggered them.
    """
    context = get_current_audit_context_with_user()
    if context is None:
        return None
    return dataclasses.asdict(context)


def audit_context_from_snapshot(snapshot: Optional[Dict[str, Any]]) -> Optional[AuditContext]:
    """Rebuild an ``AuditContext`` from ``snapshot_current_audit_context()``.

    Unknown keys are ignored so a snapshot queued by a newer version still loads.
    """
    if snapshot is None:
        return None
    known = {field.name for field in dataclasses.fields(AuditContext)}
    return AuditContext(**{key: value for key, value in snapshot.items() if key in known})
