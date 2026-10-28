"""OpenTelemetry trace correlation shared by the middleware and the explicit scopes."""

from __future__ import annotations

from typing import Optional


def get_current_trace_id() -> Optional[str]:
    """Hex trace id of the active OpenTelemetry span, or ``None`` without a valid span."""
    try:
        from opentelemetry import trace

        span_context = trace.get_current_span().get_span_context()
        if span_context and span_context.trace_id:
            return format(span_context.trace_id, "032x")
    except Exception:
        pass
    return None
