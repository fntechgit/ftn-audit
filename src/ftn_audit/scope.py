"""Explicit audit context for code that runs outside an HTTP request.

``AuditContextMiddleware`` only covers requests, and receivers drop every event
that has no context. Scheduled jobs, Celery tasks and message consumers wrap
their work in one of these helpers so their writes are audited too.
"""

from __future__ import annotations

import dataclasses
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

from ftn_audit.constants import SYSTEM_RAW_ROUTE_METHOD
from ftn_audit.context import AuditContext
from ftn_audit.context_hydration import get_current_audit_context_with_user
from ftn_audit.context_storage import enter_audit_scope, exit_audit_scope


@contextmanager
def audit_context(context: AuditContext) -> Iterator[AuditContext]:
    """Run the block under ``context``, then restore whatever was active before.

    The current request is hidden for the duration of the block, so actor
    hydration cannot attribute these writes to an unrelated request's user.
    Usable as a context manager or as a decorator.
    """
    tokens = enter_audit_scope(context)
    try:
        yield context
    finally:
        exit_audit_scope(tokens)


@contextmanager
def system_audit_context(source: str, **fields: Any) -> Iterator[AuditContext]:
    """Run the block as the system actor ``source`` (e.g. ``"job:reopen_carts"``).

    Events carry ``raw_route = "SYSTEM|<source>"``, which identifies the job or
    task in the audit trail and lets formatters register for it like any route.
    Extra ``AuditContext`` fields (e.g. ``trace_id``) can be passed as keywords.
    """
    context = AuditContext(
        route=source,
        raw_route=f"{SYSTEM_RAW_ROUTE_METHOD}|{source}",
        request_id=str(uuid.uuid4()),
        **fields,
    )
    with audit_context(context) as active:
        yield active


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
