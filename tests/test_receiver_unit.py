from __future__ import annotations

from dataclasses import dataclass

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import set_current_audit_context
from ftn_audit.generic_formatters import GenericCreationFormatter
from ftn_audit.receiver import _post_save_receiver
from ftn_audit.registry import AuditFormattersRegistry


@dataclass
class _Instance:
    pk: int


class _Model:
    __name__ = "DummyModel"


def test_post_save_creation_emits_event(monkeypatch):
    emitted = []

    class _Strategy:
        def emit(self, description, attributes):
            emitted.append((description, attributes))

    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_Model, formatter_cls=GenericCreationFormatter)

    set_current_audit_context(AuditContext(user_id=42, raw_route="POST|/v1/login/"))
    monkeypatch.setattr("ftn_audit.formatter_emitter.get_audit_strategy", lambda: _Strategy())

    _post_save_receiver(sender=_Model, instance=_Instance(pk=7), created=True)

    assert len(emitted) == 1
    description, attributes = emitted[0]
    assert description == "Created _Instance #7"
    assert attributes["audit.event_type"] == "creation"
    assert attributes["audit.raw_route"] == "POST|/v1/login/"
    assert attributes["user_id"] == 42

    set_current_audit_context(None)
    AuditFormattersRegistry.reset()
