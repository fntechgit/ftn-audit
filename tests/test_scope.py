from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from django.db import transaction

from ftn_audit import (
    AuditContext,
    audit_context,
    audit_context_from_snapshot,
    snapshot_current_audit_context,
    system_audit_context,
)
from ftn_audit import strategy as strategy_module
from ftn_audit.context_hydration import get_current_audit_context_with_user
from ftn_audit.context_storage import (
    get_current_audit_context,
    get_current_audit_request,
    set_current_audit_context,
    set_current_audit_request,
)
from ftn_audit.generic_formatters import GenericUpdateFormatter
from ftn_audit.registry import AuditFormattersRegistry
from tests.test_app.models import AuditedThing

JOB_SOURCE = "job:reopen_old_checked_out_carts"
REQUEST_CONTEXT = AuditContext(user_id=7, user_email="actor@fntech.com", raw_route="PUT|/v1/carts/:id/")


class _AuthUser:
    is_authenticated = True
    pk = 99
    email = "stale@fntech.com"
    first_name = "Stale"
    last_name = "Request"


class _RequestWithAuthUser:
    user = _AuthUser()


def setup_function():
    set_current_audit_context(None)
    set_current_audit_request(None)
    AuditFormattersRegistry.reset()
    strategy_module._strategy_instance = None


def teardown_function():
    set_current_audit_context(None)
    set_current_audit_request(None)
    AuditFormattersRegistry.reset()
    strategy_module._strategy_instance = None


def test_audit_context_sets_the_context_and_restores_the_previous_one():
    set_current_audit_context(REQUEST_CONTEXT)
    inner = AuditContext(user_id=1, raw_route="SYSTEM|task:x")

    with audit_context(inner) as active:
        assert active is inner
        assert get_current_audit_context() is inner

    assert get_current_audit_context() is REQUEST_CONTEXT


def test_audit_context_restores_the_previous_context_when_the_block_raises():
    with pytest.raises(RuntimeError):
        with audit_context(AuditContext(user_id=1)):
            raise RuntimeError("boom")

    assert get_current_audit_context() is None


def test_audit_context_hides_the_current_request_from_actor_hydration():
    # Without this, a context with no user would be hydrated from whatever
    # request happens to be stored, attributing the write to that request's user.
    request = _RequestWithAuthUser()
    set_current_audit_request(request)

    with system_audit_context(JOB_SOURCE):
        assert get_current_audit_request() is None
        assert get_current_audit_context_with_user().user_id is None

    assert get_current_audit_request() is request


def test_system_audit_context_identifies_the_source_in_raw_route():
    with system_audit_context(JOB_SOURCE) as ctx:
        assert ctx.raw_route == f"SYSTEM|{JOB_SOURCE}"
        assert ctx.route == JOB_SOURCE
        assert ctx.user_id is None
        assert ctx.request_id


def test_system_audit_context_works_as_a_decorator():
    @system_audit_context(JOB_SOURCE)
    def job():
        return get_current_audit_context()

    assert job().raw_route == f"SYSTEM|{JOB_SOURCE}"
    assert job().request_id != job().request_id
    assert get_current_audit_context() is None


def test_decorated_coroutine_keeps_the_scope_across_await():
    # A plain ContextDecorator would close the scope as soon as the coroutine object is returned.
    @system_audit_context(JOB_SOURCE)
    async def system_handler():
        await asyncio.sleep(0)
        return get_current_audit_context()

    @audit_context(REQUEST_CONTEXT)
    async def user_handler():
        await asyncio.sleep(0)
        return get_current_audit_context()

    assert asyncio.run(system_handler()).raw_route == f"SYSTEM|{JOB_SOURCE}"
    assert asyncio.run(user_handler()) is REQUEST_CONTEXT
    assert get_current_audit_context() is None


def test_reentering_the_same_scope_instance_restores_the_outer_state():
    # Per-entry state must not live on the instance: the inner exit would
    # otherwise swallow the outer one, leaving the system context and the
    # hidden request in place after the outer block ends.
    request = _RequestWithAuthUser()
    set_current_audit_request(request)
    set_current_audit_context(REQUEST_CONTEXT)
    scope = system_audit_context(JOB_SOURCE)

    with scope as outer:
        with scope as inner:
            assert get_current_audit_context() is inner
        assert get_current_audit_context() is outer
        assert get_current_audit_request() is None

    assert get_current_audit_context() is REQUEST_CONTEXT
    assert get_current_audit_request() is request


def test_one_scope_instance_can_be_shared_by_concurrent_tasks():
    # Each task exits with the tokens of its own context, whichever finishes first.
    scope = system_audit_context(JOB_SOURCE)

    async def worker(delay):
        with scope as ctx:
            await asyncio.sleep(delay)
            return get_current_audit_context() is ctx

    async def main():
        return await asyncio.gather(worker(0), worker(0.01))

    assert asyncio.run(main()) == [True, True]
    assert get_current_audit_context() is None


def test_decorating_a_generator_function_is_rejected():
    # The sync wrapper would exit the scope as soon as the generator object is
    # returned, so the body would run without a context and its writes be dropped.
    def gen():
        yield

    async def agen():
        yield

    with pytest.raises(TypeError, match="generator function"):
        system_audit_context(JOB_SOURCE)(gen)
    with pytest.raises(TypeError, match="generator function"):
        audit_context(REQUEST_CONTEXT)(agen)


def test_system_audit_context_accepts_request_metadata():
    with system_audit_context(JOB_SOURCE, trace_id="abc", ui_app="admin", ui_flow="sync") as ctx:
        assert (ctx.trace_id, ctx.ui_app, ctx.ui_flow) == ("abc", "admin", "sync")


@pytest.mark.parametrize("field", ["user_id", "user_email", "raw_route", "route", "request_id"])
def test_system_audit_context_rejects_actor_and_route_fields(field):
    # A system event must not also name a user, and its route/request_id are owned by the helper.
    # Code acting for a user should use audit_context() instead.
    with pytest.raises(TypeError):
        system_audit_context(JOB_SOURCE, **{field: 1})


def test_snapshot_round_trips_the_hydrated_context():
    set_current_audit_context(AuditContext(raw_route="DELETE|/v1/carts/current/checkout"))
    set_current_audit_request(_RequestWithAuthUser())

    snapshot = snapshot_current_audit_context()

    assert snapshot["user_id"] == 99
    assert snapshot["user_email"] == "stale@fntech.com"
    restored = audit_context_from_snapshot(snapshot)
    assert restored.user_id == 99
    assert restored.raw_route == "DELETE|/v1/carts/current/checkout"


def test_snapshot_is_none_without_a_context():
    assert snapshot_current_audit_context() is None
    assert audit_context_from_snapshot(None) is None


def test_audit_context_from_snapshot_ignores_unknown_keys():
    # A snapshot taken by a newer library version must still load.
    restored = audit_context_from_snapshot({"user_id": 3, "added_in_a_later_version": "x"})

    assert restored == AuditContext(user_id=3)


@pytest.mark.django_db(transaction=True)
def test_write_outside_a_request_is_dropped_without_a_context(settings):
    settings.AUDIT_ENABLED = True
    obj = AuditedThing.objects.create(name="old")
    AuditFormattersRegistry.register(AuditedThing, GenericUpdateFormatter, event_type="update")

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with transaction.atomic():
            obj.name = "new"
            obj.save()

    delay_mock.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_write_inside_system_audit_context_is_emitted_with_the_source(settings):
    settings.AUDIT_ENABLED = True
    obj = AuditedThing.objects.create(name="old")
    AuditFormattersRegistry.register(AuditedThing, GenericUpdateFormatter, event_type="update")

    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        with system_audit_context(JOB_SOURCE), transaction.atomic():
            obj.name = "new"
            obj.save()

    delay_mock.assert_called_once()
    attributes = delay_mock.call_args.args[0]["attributes"]
    assert attributes["audit.raw_route"] == f"SYSTEM|{JOB_SOURCE}"
    assert attributes["audit.changeset"]["name"]["new"] == "new"
    assert attributes["user_id"] is None
