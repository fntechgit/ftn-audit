from __future__ import annotations

from dataclasses import dataclass

import pytest

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import set_current_audit_context, set_current_audit_request
from ftn_audit.generic_formatters import GenericCreationFormatter
from ftn_audit.receiver import _post_save_receiver, _pre_save_receiver
from ftn_audit.registry import AuditFormattersRegistry


@dataclass
class _Instance:
    pk: int


class _Model:
    __name__ = "DummyModel"


class _InvalidFormatter:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


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
    set_current_audit_request(None)
    AuditFormattersRegistry.reset()


def test_post_save_creation_hydrates_user_from_request_when_context_user_missing(monkeypatch):
    emitted = []

    class _Strategy:
        def emit(self, description, attributes):
            emitted.append((description, attributes))

    class _RequestUser:
        is_authenticated = True
        pk = 77
        email = "actor@test.local"
        first_name = "Actor"
        last_name = "User"

    class _Request:
        user = _RequestUser()

    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_Model, formatter_cls=GenericCreationFormatter)

    set_current_audit_context(AuditContext(user_id=None, raw_route="POST|/v1/x/"))
    set_current_audit_request(_Request())
    monkeypatch.setattr("ftn_audit.formatter_emitter.get_audit_strategy", lambda: _Strategy())

    _post_save_receiver(sender=_Model, instance=_Instance(pk=9), created=True)

    assert len(emitted) == 1
    _, attributes = emitted[0]
    assert attributes["user_id"] == 77
    assert attributes["user_email"] == "actor@test.local"

    set_current_audit_context(None)
    set_current_audit_request(None)
    AuditFormattersRegistry.reset()


def test_pre_save_skips_raw_fixture_load(monkeypatch):
    calls = []

    class _InstanceWithRaw:
        pk = 7

    def _fake_build_changeset(_instance):
        calls.append("called")
        return {"name": {"old": "a", "new": "b"}}

    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_Model, formatter_cls=GenericCreationFormatter)
    monkeypatch.setattr("ftn_audit.receiver.build_changeset", _fake_build_changeset)

    instance = _InstanceWithRaw()
    _pre_save_receiver(sender=_Model, instance=instance, raw=True)

    assert calls == []
    assert not hasattr(instance, "_ftn_audit_pending_changeset")
    AuditFormattersRegistry.reset()


def test_pre_save_filters_changeset_to_update_fields(monkeypatch):
    class _Field:
        def __init__(self, name: str, attname: str):
            self.name = name
            self.attname = attname

    class _Meta:
        fields = [_Field("name", "name"), _Field("owner", "owner_id")]

    class _InstanceWithMeta:
        pk = 7
        _meta = _Meta()

    def _fake_build_changeset(_instance):
        return {
            "name": {"old": "a", "new": "b"},
            "owner": {"old": 1, "new": 2},
        }

    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_Model, formatter_cls=GenericCreationFormatter)
    monkeypatch.setattr("ftn_audit.receiver.build_changeset", _fake_build_changeset)

    instance = _InstanceWithMeta()
    _pre_save_receiver(sender=_Model, instance=instance, update_fields={"name"})

    assert getattr(instance, "_ftn_audit_pending_changeset") == {
        "name": {"old": "a", "new": "b"}
    }
    AuditFormattersRegistry.reset()


def test_strict_formatter_validation_propagates_from_post_save():
    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_Instance, formatter_cls=_InvalidFormatter)

    set_current_audit_context(AuditContext(user_id=55, raw_route="POST|/v1/test/"))

    with pytest.raises(TypeError, match="Invalid audit formatter instance"):
        _post_save_receiver(sender=_Instance, instance=_Instance(pk=12), created=True)

    set_current_audit_context(None)
    set_current_audit_request(None)
    AuditFormattersRegistry.reset()
