# ftn-audit — Testing Patterns

## Test Isolation (Critical)

Every test that touches audit must reset shared state in setup AND teardown:

```python
from ftn_audit.registry import AuditFormattersRegistry
from ftn_audit.collections_registry import AuditCollectionsRegistry
from ftn_audit.context_storage import set_current_audit_context
from ftn_audit import strategy as strategy_module

# Before test
AuditFormattersRegistry.reset()
AuditCollectionsRegistry.reset()
strategy_module._strategy_instance = None
set_current_audit_context(AuditContext(user_id=1, raw_route="POST|/test/"))

# After test (in finally or teardown)
set_current_audit_context(None)
AuditFormattersRegistry.reset()
AuditCollectionsRegistry.reset()
strategy_module._strategy_instance = None
```

**Why:** Registry and strategy are module-level singletons. Without reset, tests pollute each other.

## transaction=True Required

Use `@pytest.mark.django_db(transaction=True)` for any test that triggers audit signals. Audit emission defers to `transaction.on_commit` — without real transactions, the callback never fires.

## Mocking Celery Task

Always mock `ftn_audit.tasks.emit_audit_log_task.delay` — never let tests hit a real broker:

```python
with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
    with transaction.atomic():
        obj = AuditedThing.objects.create(name="test")

payload = delay_mock.call_args.args[0]
assert payload["attributes"]["audit.event_type"] == "creation"
```

## Testing on_commit Callbacks Without DB

For unit tests that don't need the database, mock `transaction.on_commit`:

```python
callbacks = []
with patch("django.db.transaction.on_commit", side_effect=lambda cb: callbacks.append(cb)):
    with patch("ftn_audit.tasks.emit_audit_log_task.delay") as delay_mock:
        OtlpAuditStrategy().emit("desc", {"key": "val"})
        callbacks[0]()  # manually fire the on_commit callback

delay_mock.assert_called_once()
```

## Test App Models

Located in `tests/test_app/models.py`:
- `AuditedThing` — basic model with `DirtyFieldsMixin` (name field)
- `Tag` — plain model (M2M target)
- `AuditedBasket` — model with `tags = ManyToManyField(Tag)` for M2M tests

## Running Tests

```bash
pytest -q                                           # All tests
pytest tests/test_receiver_integration.py -q       # Integration only
pytest --cov=src/ftn_audit --cov-fail-under=80     # With coverage
```
