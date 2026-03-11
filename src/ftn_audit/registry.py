"""Formatter registry — maps (model, raw_route, event_type) → formatter class."""

from __future__ import annotations

import dataclasses
import logging
from typing import Dict, List, Optional, Tuple, Type

logger = logging.getLogger("audit")


@dataclasses.dataclass(frozen=True)
class FormatterRule:
    model: type
    formatter_cls: type
    raw_route: Optional[str] = None
    event_type: Optional[str] = None
    priority: int = 0


class AuditFormattersRegistry:
    _rules: Dict[type, List[FormatterRule]] = {}

    @classmethod
    def register(
        cls,
        model: type,
        formatter_cls: type,
        raw_route: Optional[str] = None,
        event_type: Optional[str] = None,
        priority: int = 0,
    ) -> None:
        rule = FormatterRule(
            model=model,
            formatter_cls=formatter_cls,
            raw_route=raw_route,
            event_type=event_type,
            priority=priority,
        )
        cls._rules.setdefault(model, []).append(rule)
        cls._rules[model].sort(key=lambda r: -r.priority)

    @classmethod
    def has_model(cls, model: type) -> bool:
        return model in cls._rules

    @classmethod
    def find(
        cls,
        model: type,
        raw_route: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> Optional[Type]:
        rules = cls._rules.get(model)
        if not rules:
            return None
        # 1. exact route + event match
        for r in rules:
            if r.raw_route and r.event_type:
                if r.raw_route == raw_route and r.event_type == event_type:
                    return r.formatter_cls
        # 2. route-only match
        for r in rules:
            if r.raw_route and not r.event_type and r.raw_route == raw_route:
                return r.formatter_cls
        # 3. event-only match
        for r in rules:
            if r.event_type and not r.raw_route and r.event_type == event_type:
                return r.formatter_cls
        # 4. model default (no route, no event)
        for r in rules:
            if not r.raw_route and not r.event_type:
                return r.formatter_cls
        return None

    @classmethod
    def reset(cls) -> None:
        """Clear all registrations — for test isolation."""
        cls._rules.clear()


def register_audit_formatter(
    model: type,
    raw_route: Optional[str] = None,
    event_type: Optional[str] = None,
    priority: int = 0,
):
    """Decorator that registers a formatter class for *model*."""

    def decorator(formatter_cls):
        AuditFormattersRegistry.register(
            model=model,
            formatter_cls=formatter_cls,
            raw_route=raw_route,
            event_type=event_type,
            priority=priority,
        )
        return formatter_cls

    return decorator
