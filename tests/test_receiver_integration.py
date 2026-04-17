from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import transaction

from ftn_audit.context import AuditContext
from ftn_audit.context_storage import set_current_audit_context
from ftn_audit.generic_formatters import (
    GenericCreationFormatter,
    GenericDeletionFormatter,
    GenericUpdateFormatter,
)
from ftn_audit.registry import AuditFormattersRegistry
from ftn_audit.collections_registry import AuditCollectionsRegistry, register_audit_collection
from ftn_audit import strategy as strategy_module
from tests.test_app.models import AuditedBasket, AuditedThing, Tag


@pytest.mark.django_db(transaction=True)
def test_create_model_emits_audit_event_after_commit(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditFormattersRegistry.reset()
    AuditFormattersRegistry.register(AuditedThing, GenericCreationFormatter)
    set_current_audit_context(AuditContext(user_id=9, raw_route="POST|/v1/login/"))

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            obj = AuditedThing.objects.create(name="first")

    delay_mock.assert_called_once()
    payload = delay_mock.call_args.args[0]
    assert payload["description"] == f"Created AuditedThing #{obj.pk}"
    assert payload["attributes"]["audit.event_type"] == "creation"
    assert payload["attributes"]["audit.model"] == "AuditedThing"
    assert payload["attributes"]["audit.raw_route"] == "POST|/v1/login/"
    assert payload["attributes"]["user_id"] == 9

    set_current_audit_context(None)
    AuditFormattersRegistry.reset()
    strategy_module._strategy_instance = None


@pytest.mark.django_db(transaction=True)
def test_update_model_emits_changeset_after_commit(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditFormattersRegistry.reset()
    obj = AuditedThing.objects.create(name="old")
    AuditFormattersRegistry.register(AuditedThing, GenericUpdateFormatter, event_type="update")
    set_current_audit_context(AuditContext(user_id=20, raw_route="PATCH|/v1/things/:id/"))

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            obj.name = "new"
            obj.save()

    payload = delay_mock.call_args.args[0]
    assert payload["attributes"]["audit.event_type"] == "update"
    assert payload["attributes"]["audit.changeset"]["name"]["old"] == "old"
    assert payload["attributes"]["audit.changeset"]["name"]["new"] == "new"

    set_current_audit_context(None)
    AuditFormattersRegistry.reset()
    strategy_module._strategy_instance = None


@pytest.mark.django_db(transaction=True)
def test_delete_model_emits_event_after_commit(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditFormattersRegistry.reset()
    obj = AuditedThing.objects.create(name="bye")
    AuditFormattersRegistry.register(AuditedThing, GenericDeletionFormatter, event_type="deletion")
    set_current_audit_context(AuditContext(user_id=21, raw_route="DELETE|/v1/things/:id/"))

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            obj.delete()

    payload = delay_mock.call_args.args[0]
    assert payload["attributes"]["audit.event_type"] == "deletion"
    assert payload["attributes"]["audit.model"] == "AuditedThing"

    set_current_audit_context(None)
    AuditFormattersRegistry.reset()
    strategy_module._strategy_instance = None


@pytest.mark.django_db(transaction=True)
def test_m2m_add_emits_event(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditCollectionsRegistry.reset()
    set_current_audit_context(AuditContext(user_id=30, raw_route="POST|/v1/basket/:id/tags/"))

    register_audit_collection(AuditedBasket, "tags")
    basket = AuditedBasket.objects.create(name="Basket A")
    tag = Tag.objects.create(label="x")

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            basket.tags.add(tag)

    payload = delay_mock.call_args.args[0]
    assert payload["attributes"]["audit.event_type"] == "collection_update"
    assert payload["attributes"]["audit.raw_route"] == "POST|/v1/basket/:id/tags/"
    assert payload["attributes"]["audit.field_name"] == "tags"
    assert payload["attributes"]["audit.action"] == "post_add"
    assert payload["attributes"]["audit.pk_set"] == [tag.pk]

    set_current_audit_context(None)
    AuditCollectionsRegistry.reset()
    strategy_module._strategy_instance = None


@pytest.mark.django_db(transaction=True)
def test_m2m_remove_emits_event(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditCollectionsRegistry.reset()
    register_audit_collection(AuditedBasket, "tags")

    basket = AuditedBasket.objects.create(name="Basket B")
    tag = Tag.objects.create(label="y")
    basket.tags.add(tag)
    set_current_audit_context(AuditContext(user_id=31, raw_route="DELETE|/v1/basket/:id/tags/:tag_id/"))

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            basket.tags.remove(tag)

    payload = delay_mock.call_args.args[0]
    assert payload["attributes"]["audit.action"] == "post_remove"
    assert payload["attributes"]["audit.pk_set"] == [tag.pk]

    set_current_audit_context(None)
    AuditCollectionsRegistry.reset()
    strategy_module._strategy_instance = None


@pytest.mark.django_db(transaction=True)
def test_m2m_clear_emits_event(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditCollectionsRegistry.reset()
    register_audit_collection(AuditedBasket, "tags")

    basket = AuditedBasket.objects.create(name="Basket C")
    tag1 = Tag.objects.create(label="a")
    tag2 = Tag.objects.create(label="b")
    basket.tags.add(tag1, tag2)
    set_current_audit_context(AuditContext(user_id=32, raw_route="DELETE|/v1/basket/:id/tags/"))

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            basket.tags.clear()

    payload = delay_mock.call_args.args[0]
    assert payload["attributes"]["audit.action"] == "post_clear"
    assert payload["attributes"]["audit.pk_set"] == sorted([tag1.pk, tag2.pk])

    set_current_audit_context(None)
    AuditCollectionsRegistry.reset()
    strategy_module._strategy_instance = None


@pytest.mark.django_db(transaction=True)
def test_m2m_reverse_side_does_not_emit_event(settings):
    settings.AUDIT_ENABLED = True
    strategy_module._strategy_instance = None
    AuditCollectionsRegistry.reset()
    register_audit_collection(AuditedBasket, "tags")
    set_current_audit_context(AuditContext(user_id=33, raw_route="POST|/v1/tags/:id/baskets/"))

    basket = AuditedBasket.objects.create(name="Basket D")
    tag = Tag.objects.create(label="reverse")

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            tag.baskets.add(basket)

    delay_mock.assert_not_called()

    set_current_audit_context(None)
    AuditCollectionsRegistry.reset()
    strategy_module._strategy_instance = None
