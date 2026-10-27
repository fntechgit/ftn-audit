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
from ftn_audit.context_storage import enter_audit_scope, exit_audit_scope
from ftn_audit.tracing import get_current_trace_id

F = TypeVar("F", bound=Callable[..., Any])


class AuditScope:
    """Context manager and decorator that makes an ``AuditContext`` current.

    The context is built on every entry, so a decorated function gets a fresh
    one per call. The scope keeps no per-entry state, so one instance can be
    re-entered or shared between tasks and threads. Decorated coroutine
    functions keep the scope across ``await`` (a plain ``ContextDecorator``
    would close it before the body runs), also behind ``functools.wraps``
    wrappers. Generator functions (also behind wrappers), and sync wrappers
    that hide a coroutine or generator without ``__wrapped__``, are rejected
    with ``TypeError``: the scope would close before the body runs, dropping
    its writes silently.
    """

    def __init__(self, make_context: Callable[[], AuditContext]) -> None:
        self._make_context = make_context

    def __enter__(self) -> AuditContext:
        context = self._make_context()
        enter_audit_scope(context)
        return context

    def __exit__(self, *exc_info: Any) -> None:
        exit_audit_scope()

    def __call__(self, func: F) -> F:
        make_context = self._make_context

        # Follow ``__wrapped__`` so a coroutine or generator function behind a
        # sync wrapper (e.g. ``@inject_job``) is still recognized.
        target = inspect.unwrap(func)

        if any(
            check(candidate)
            for candidate in (func, target)
            for check in (inspect.isgeneratorfunction, inspect.isasyncgenfunction)
        ):
            raise TypeError(
                f"{getattr(func, '__qualname__', func)!r} is a generator function; an audit scope "
                "cannot decorate it. Open the scope with a `with` block inside the generator instead."
            )

        # Either side may be the coroutine function: a sync wrapper over an
        # ``async def``, or an ``async def`` wrapper (``sync_to_async``) over a
        # sync target.
        if inspect.iscoroutinefunction(func) or inspect.iscoroutinefunction(target):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with AuditScope(make_context):
                    return await func(*args, **kwargs)

            return cast(F, async_wrapper)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with AuditScope(make_context):
                result = func(*args, **kwargs)
            deferred = _deferred_result_kind(result)
            if deferred is not None:
                # A wrapper without ``__wrapped__`` hid a coroutine or generator:
                # the scope is already closed before its body runs, so fail
                # loudly instead of dropping its writes.
                close = getattr(result, "close", None)
                if callable(close):
                    close()
                raise TypeError(
                    f"{getattr(func, '__qualname__', func)!r} returned {deferred}; decorate the "
                    "coroutine or generator function directly or open the scope inside it."
                )
            return result

        return cast(F, wrapper)


def _deferred_result_kind(result: Any) -> Optional[str]:
    """Name the kind of lazily-executed object ``result`` is, or ``None`` for a plain value."""
    if inspect.isawaitable(result):
        return "an awaitable"
    if inspect.isgenerator(result) or inspect.isasyncgen(result):
        return "a generator"
    return None


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
    ``request_id`` per entry. ``trace_id`` defaults to the OpenTelemetry span
    active when the scope is entered, like the middleware does for requests.
    Only request metadata can be added: code acting on behalf of a user should
    use ``audit_context()`` with that user instead.
    """
    raw_route = f"{SYSTEM_RAW_ROUTE_METHOD}|{source}"
    return AuditScope(lambda: AuditContext(
        route=source,
        raw_route=raw_route,
        request_id=str(uuid.uuid4()),
        trace_id=trace_id if trace_id is not None else get_current_trace_id(),
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
