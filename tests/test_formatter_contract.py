from __future__ import annotations

from dataclasses import dataclass

import pytest

from ftn_audit.base_formatter import AbstractAuditLogFormatter
from ftn_audit.context import AuditContext
from ftn_audit.formatter_factory import AuditLogFormatterFactory
from ftn_audit.registry import AuditFormattersRegistry


@dataclass
class _Instance:
    pk: int


class _Model:
    __name__ = "DummyModel"


class _SuperFormatter(AbstractAuditLogFormatter):
    def get_description(self) -> str:
        return "ok"

    def get_attributes(self):
        attrs = super().get_attributes()
        attrs["custom"] = "yes"
        return attrs


class _InvalidFormatter:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_super_get_attributes_is_safe():
    formatter = _SuperFormatter(
        context=AuditContext(user_id=12),
        subject=_Instance(pk=8),
        event_type="update",
        changeset={"name": {"old": "a", "new": "b"}},
    )

    attrs = formatter.get_attributes()

    assert attrs["audit.event_type"] == "update"
    assert attrs["audit.model"] == "_Instance"
    assert attrs["audit.model_pk"] == "8"
    assert attrs["audit.changeset"]["name"]["old"] == "a"
    assert attrs["custom"] == "yes"


def test_invalid_formatter_raises_actionable_error():
    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_Instance, _InvalidFormatter)

    with pytest.raises(TypeError, match="Invalid audit formatter instance"):
        AuditLogFormatterFactory.make(
            ctx=AuditContext(raw_route="GET|/v1/test/"),
            subject=_Instance(pk=1),
            event_type="update",
            changeset=None,
        )

    AuditFormattersRegistry.reset()


def test_invalid_formatter_logs_when_strict_disabled(settings, caplog):
    settings.AUDIT_STRICT_FORMATTER_VALIDATION = False
    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_Instance, _InvalidFormatter)

    with caplog.at_level("ERROR", logger="audit"):
        formatter = AuditLogFormatterFactory.make(
            ctx=AuditContext(raw_route="GET|/v1/test/"),
            subject=_Instance(pk=1),
            event_type="update",
            changeset=None,
        )

    assert isinstance(formatter, _InvalidFormatter)
    assert "Invalid audit formatter instance" in caplog.text

    AuditFormattersRegistry.reset()
