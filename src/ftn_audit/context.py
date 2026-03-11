"""Immutable audit context carried through the request lifecycle."""

from __future__ import annotations

import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class AuditContext:
    """Snapshot of request-scoped information captured by middleware."""

    user_id: Optional[int] = None
    user_email: Optional[str] = None
    user_first_name: Optional[str] = None
    user_last_name: Optional[str] = None
    http_method: Optional[str] = None
    route: Optional[str] = None
    raw_route: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    ui_app: Optional[str] = None
    ui_flow: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None
