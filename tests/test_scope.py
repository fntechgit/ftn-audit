from __future__ import annotations

import asyncio
import functools
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
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


def test_decorated_coroutine_behind_a_wraps_wrapper_keeps_the_scope():
    # Decorator stacks such as @system_audit_context over @inject_job hand the
    # scope a sync wrapper; it must still detect the coroutine underneath.
    async def handler():
        await asyncio.sleep(0)
        return get_current_audit_context()

    @functools.wraps(handler)
    def sync_wrapper(*args, **kwargs):
        return handler(*args, **kwargs)

    decorated = system_audit_context(JOB_SOURCE)(sync_wrapper)

    assert asyncio.run(decorated()).raw_route == f"SYSTEM|{JOB_SOURCE}"
    assert get_current_audit_context() is None


def test_decorated_async_wrapper_over_a_sync_target_keeps_the_scope():
    # sync_to_async(handler) is a coroutine function whose __wrapped__ is the
    # sync handler; the async path must be chosen from the outer callable too,
    # not only from the unwrapped target.
    def handler():
        return get_current_audit_context()

    @functools.wraps(handler)
    async def async_wrapper(*args, **kwargs):
        return await sync_to_async(handler)(*args, **kwargs)

    for func in (async_wrapper, sync_to_async(handler)):
        decorated = system_audit_context(JOB_SOURCE)(func)
        assert asyncio.run(decorated()).raw_route == f"SYSTEM|{JOB_SOURCE}"
        assert get_current_audit_context() is None


def test_sync_wrapper_hiding_a_coroutine_without_wrapped_is_rejected():
    # Without __wrapped__ the coroutine cannot be detected up front and the
    # scope is already closed when the awaitable comes back: fail loudly.
    async def handler():
        return None

    def opaque_wrapper():
        return handler()

    decorated = system_audit_context(JOB_SOURCE)(opaque_wrapper)

    with pytest.raises(TypeError, match="returned an awaitable"):
        decorated()
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


def test_decorating_a_generator_function_behind_a_wraps_wrapper_is_rejected():
    # @inject_job-style wrappers expose the generator through __wrapped__; the
    # guard must look through them like it does for coroutine functions.
    def gen():
        yield

    @functools.wraps(gen)
    def sync_wrapper(*args, **kwargs):
        return gen(*args, **kwargs)

    with pytest.raises(TypeError, match="generator function"):
        system_audit_context(JOB_SOURCE)(sync_wrapper)


def test_sync_wrapper_returning_a_generator_without_wrapped_is_rejected():
    # Without __wrapped__ the generator cannot be detected up front; the scope is
    # already closed when the generator object comes back, so iterating it would
    # run the body with no context. Fail loudly instead.
    def gen():
        yield get_current_audit_context()

    def opaque_wrapper():
        return gen()

    decorated = system_audit_context(JOB_SOURCE)(opaque_wrapper)

    with pytest.raises(TypeError, match="returned a generator"):
        decorated()
    assert get_current_audit_context() is None


def test_system_audit_context_accepts_request_metadata():
    with system_audit_context(JOB_SOURCE, trace_id="abc", ui_app="admin", ui_flow="sync") as ctx:
        assert (ctx.trace_id, ctx.ui_app, ctx.ui_flow) == ("abc", "admin", "sync")


def test_system_audit_context_takes_the_trace_id_from_the_active_span():
    # Jobs run under a tracing span (purchases-api's @traced_job); like the
    # middleware, the helper correlates its events with that span unless a
    # trace_id is given explicitly.
    from opentelemetry.sdk.trace import TracerProvider

    tracer = TracerProvider().get_tracer("tests")

    with tracer.start_as_current_span("job reopen") as span:
        expected = format(span.get_span_context().trace_id, "032x")
        with system_audit_context(JOB_SOURCE) as ctx:
            assert ctx.trace_id == expected
        with system_audit_context(JOB_SOURCE, trace_id="explicit") as ctx:
            assert ctx.trace_id == "explicit"

    with system_audit_context(JOB_SOURCE) as ctx:
        assert ctx.trace_id is None


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
