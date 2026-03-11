"""M2M collection registry — allowlist of many-to-many relations that should be audited."""

from __future__ import annotations

import dataclasses
import logging
from typing import Dict, Optional, Type

logger = logging.getLogger("audit.m2m")


@dataclasses.dataclass(frozen=True)
class CollectionRule:
    owner_model: type
    field_name: str
    through_model: type
    formatter_cls: Optional[Type] = None


class AuditCollectionsRegistry:
    _by_through: Dict[type, CollectionRule] = {}
    _by_owner_field: Dict[tuple, CollectionRule] = {}

    @classmethod
    def register(
        cls,
        owner_model: type,
        field_name: str,
        through_model: type,
        formatter_cls: Optional[Type] = None,
    ) -> None:
        rule = CollectionRule(
            owner_model=owner_model,
            field_name=field_name,
            through_model=through_model,
            formatter_cls=formatter_cls,
        )
        cls._by_through[through_model] = rule
        cls._by_owner_field[(owner_model, field_name)] = rule

    @classmethod
    def find_by_through(cls, through_model: type) -> Optional[CollectionRule]:
        return cls._by_through.get(through_model)

    @classmethod
    def find_by_owner_field(cls, owner_model: type, field_name: str) -> Optional[CollectionRule]:
        return cls._by_owner_field.get((owner_model, field_name))

    @classmethod
    def reset(cls) -> None:
        cls._by_through.clear()
        cls._by_owner_field.clear()


def register_audit_collection(
    owner_model: type,
    field_name: str,
    formatter_cls: Optional[Type] = None,
):
    """Decorator/call that registers an M2M field for audit collection tracking."""

    m2m_field = owner_model._meta.get_field(field_name)
    through_model = m2m_field.remote_field.through

    AuditCollectionsRegistry.register(
        owner_model=owner_model,
        field_name=field_name,
        through_model=through_model,
        formatter_cls=formatter_cls,
    )
