from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import transaction

from ftn_audit import strategy as strategy_module
from ftn_audit.autodiscover import autodiscover_formatters
from ftn_audit.collections_registry import AuditCollectionsRegistry
from ftn_audit.context import AuditContext
from ftn_audit.context_storage import set_current_audit_context
from ftn_audit.formatter_factory import AuditLogFormatterFactory
from ftn_audit.generic_formatters import (
    GenericCreationFormatter,
    GenericUpdateFormatter,
)
from ftn_audit.middleware import AuditContextMiddleware
from ftn_audit.registry import AuditFormattersRegistry
from tests.test_app.models import AuditedBasket, AuditedThing, Tag


class _DefaultFormatter(GenericUpdateFormatter):
    pass


class _RouteFormatter(GenericUpdateFormatter):
    pass


class _RegisteredModel:
    __name__ = "RegisteredModel"


class _UnregisteredModel:
    __name__ = "UnregisteredModel"


def test_autodiscovery_imports_file_and_package_audit_formatters(monkeypatch):
    file_app = "tests._audit_file_app"
    pkg_app = "tests._audit_pkg_app"
    file_mod = f"{file_app}.audit_formatters"
    pkg_mod = f"{pkg_app}.audit_formatters"

    modules = {}
    for parent in (file_app, pkg_app):
        parent_module = ModuleType(parent)
        parent_module.__path__ = []
        modules[parent] = parent_module

    modules[file_mod] = ModuleType(file_mod)
    pkg_module = ModuleType(pkg_mod)
    pkg_module.__path__ = ["/virtual/audit_formatters"]
    modules[pkg_mod] = pkg_module

    created = []
    for name, module in modules.items():
        if name not in sys.modules:
            sys.modules[name] = module
            created.append(name)

    monkeypatch.setattr(
        "ftn_audit.autodiscover.apps.get_app_configs",
        lambda: [SimpleNamespace(name=file_app), SimpleNamespace(name=pkg_app)],
    )

    try:
        autodiscover_formatters()
        assert file_mod in sys.modules
        assert pkg_mod in sys.modules
    finally:
        for name in created:
            sys.modules.pop(name, None)


def test_middleware_builds_canonical_raw_route_for_path_converters():
    request = SimpleNamespace(
        method="PATCH",
        path="/v1/things/123/",
        resolver_match=SimpleNamespace(route="v1/things/<int:id>/<slug:code>/"),
    )

    raw_route = AuditContextMiddleware._build_raw_route(request)

    assert raw_route == "PATCH|/v1/things/:id/:code/"


def test_registry_selection_prefers_raw_route_then_default_then_generic():
    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(_RegisteredModel, _DefaultFormatter)
    AuditFormattersRegistry.register(
        _RegisteredModel,
        _RouteFormatter,
        raw_route="PATCH|/v1/things/:id/",
    )

    route_formatter = AuditLogFormatterFactory.make(
        ctx=AuditContext(raw_route="PATCH|/v1/things/:id/"),
        subject=_RegisteredModel(),
        event_type="update",
        changeset=None,
    )
    assert isinstance(route_formatter, _RouteFormatter)

    default_formatter = AuditLogFormatterFactory.make(
        ctx=AuditContext(raw_route="PATCH|/v1/other/:id/"),
        subject=_RegisteredModel(),
        event_type="update",
        changeset=None,
    )
    assert isinstance(default_formatter, _DefaultFormatter)

    generic_formatter = AuditLogFormatterFactory.make(
        ctx=AuditContext(raw_route="PATCH|/v1/none/:id/"),
        subject=_UnregisteredModel(),
        event_type="update",
        changeset=None,
    )
    assert isinstance(generic_formatter, GenericUpdateFormatter)

    AuditFormattersRegistry.reset()


@pytest.mark.django_db(transaction=True)
def test_m2m_receiver_only_fires_for_allowlisted_collections(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditCollectionsRegistry.reset()
    set_current_audit_context(AuditContext(user_id=50, raw_route="POST|/v1/basket/:id/tags/"))

    basket = AuditedBasket.objects.create(name="No allowlist")
    tag = Tag.objects.create(label="x")

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            basket.tags.add(tag)

    delay_mock.assert_not_called()

    set_current_audit_context(None)
    AuditCollectionsRegistry.reset()
    strategy_module._strategy_instance = None


@pytest.mark.django_db(transaction=True)
def test_commit_safety_rollback_prevents_enqueue(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(AuditedThing, GenericCreationFormatter)
    set_current_audit_context(AuditContext(user_id=51, raw_route="POST|/v1/things/"))

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with pytest.raises(RuntimeError, match="force rollback"):
            with transaction.atomic():
                AuditedThing.objects.create(name="rollback")
                raise RuntimeError("force rollback")

    delay_mock.assert_not_called()

    set_current_audit_context(None)
    AuditFormattersRegistry.reset()
    strategy_module._strategy_instance = None
