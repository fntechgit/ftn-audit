"""Shared parent emitter for formatter execution and error handling."""

from __future__ import annotations

import logging
from typing import Callable, Iterable

from ftn_audit.base_formatter import IAuditLogFormatter
from ftn_audit.strategy import get_audit_strategy


class FormatterEmitter:
    """Parent utility to centralize formatter emission behavior."""

    def __init__(self, logger: logging.Logger) -> None:
        self.logger = logger

    def emit(
        self,
        formatter_factory: Callable[[], IAuditLogFormatter],
        *,
        not_implemented_message: str,
        not_implemented_args: Iterable[object] = (),
        failure_message: str,
        failure_args: Iterable[object] = (),
    ) -> None:
        try:
            formatter = formatter_factory()
            strategy = get_audit_strategy()
            strategy.emit(formatter.get_description(), formatter.get_attributes())
        except NotImplementedError:
            self.logger.exception(not_implemented_message, *not_implemented_args)
        except Exception:
            self.logger.exception(failure_message, *failure_args)
