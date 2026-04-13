from __future__ import annotations

import datetime
import decimal
import enum
import uuid

import pytest

from ftn_audit.changeset import build_changeset
from ftn_audit.serialization import make_json_safe
from tests.test_app.models import AuditedThing, Tag


class _SampleEnum(enum.Enum):
    ACTIVE = "active"


@pytest.mark.django_db
def test_build_changeset_with_dirtyfieldsmixin_returns_old_and_new_values():
    thing = AuditedThing.objects.create(name="old-name")
    thing.name = "new-name"

    changeset = build_changeset(thing)

    assert changeset == {
        "name": {
            "old": "old-name",
            "new": "new-name",
        }
    }


def test_build_changeset_defaults_check_relationship_to_true():
    class _DirtyMock:
        def __init__(self):
            self.name = "new"
            self.kwargs = None

        def get_dirty_fields(self, **kwargs):
            self.kwargs = kwargs
            return {"name": "old"}

    instance = _DirtyMock()
    changeset = build_changeset(instance)

    assert changeset == {"name": {"old": "old", "new": "new"}}
    assert instance.kwargs == {"check_relationship": True}


def test_build_changeset_allows_overriding_check_relationship():
    class _DirtyMock:
        def __init__(self):
            self.name = "new"
            self.kwargs = None

        def get_dirty_fields(self, **kwargs):
            self.kwargs = kwargs
            return {"name": "old"}

    instance = _DirtyMock()
    build_changeset(instance, check_relationship=True)

    assert instance.kwargs == {"check_relationship": True}


def test_make_json_safe_serializes_supported_types_recursively():
    now = datetime.datetime(2026, 3, 24, 10, 15, 30, tzinfo=datetime.timezone.utc)
    today = datetime.date(2026, 3, 24)
    at_time = datetime.time(10, 15, 30)
    event_id = uuid.uuid4()
    model = Tag(id=77, label="alpha")
    opaque = object()

    payload = {
        9: decimal.Decimal("10.50"),
        "now": now,
        "today": today,
        "at_time": at_time,
        "event_id": event_id,
        "status": _SampleEnum.ACTIVE,
        "model": model,
        "collection": {1, 2},
        "nested": {"tuple": ("x", None, True)},
        "opaque": opaque,
    }

    safe = make_json_safe(payload)

    assert safe["9"] == "10.50"
    assert safe["now"] == now.isoformat()
    assert safe["today"] == today.isoformat()
    assert safe["at_time"] == at_time.isoformat()
    assert safe["event_id"] == str(event_id)
    assert safe["status"] == "active"
    assert safe["model"] == 77
    assert sorted(safe["collection"]) == [1, 2]
    assert safe["nested"]["tuple"] == ["x", None, True]
    assert safe["opaque"] == str(opaque)


def test_make_json_safe_handles_recursive_structures():
    recursive = {"name": "root"}
    recursive["self"] = recursive

    safe = make_json_safe(recursive)

    assert safe["name"] == "root"
    assert safe["self"] == "<recursive_ref>"
