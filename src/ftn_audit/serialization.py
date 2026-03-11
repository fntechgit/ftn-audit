"""JSON-safe value conversion for audit changeset payloads."""

from __future__ import annotations

import datetime
import decimal
import enum
import uuid
from typing import Any

from django.db import models


def make_json_safe(value: Any) -> Any:
    """Recursively convert *value* to a JSON-serialisable form."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, dict):
        return {str(k): make_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [make_json_safe(v) for v in value]
    # Fallback
    return str(value)
