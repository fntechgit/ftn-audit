from __future__ import annotations

from dataclasses import dataclass

from ftn_audit.constants import M2M_PK_SET_MAX
from ftn_audit.context import AuditContext
from ftn_audit.generic_formatters import GenericCollectionUpdateFormatter
from ftn_audit.m2m_receiver import _cap_pk_set


@dataclass
class _Subject:
    pk: int


def test_m2m_receiver_caps_pk_set_size():
    capped = _cap_pk_set(range(0, M2M_PK_SET_MAX + 120))

    assert len(capped) == M2M_PK_SET_MAX


def test_collection_formatter_does_not_cap_pk_set_size():
    formatter = GenericCollectionUpdateFormatter(
        context=AuditContext(user_id=1),
        subject=_Subject(pk=9),
        event_type="collection_update",
        field_name="tags",
        pk_set=set(range(0, M2M_PK_SET_MAX + 120)),
        action="post_add",
    )

    attrs = formatter.get_attributes()

    assert len(attrs["audit.pk_set"]) == M2M_PK_SET_MAX + 120
