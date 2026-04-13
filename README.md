# ftn-audit

Shared Django/DRF audit logging library with asynchronous OTLP delivery via Celery.

## What this package includes

- Request and user context capture via middleware (`AuditContextMiddleware`)
- Signal receivers (`pre_save`, `post_save`, `post_delete`, `m2m_changed`)
- Formatter registry with route-aware and event-aware selection
- Generic formatter fallback when no custom formatter is registered
- Delivery strategies (`NoopAuditStrategy`, `OtlpAuditStrategy`)
- Celery task for OTLP emission
- Unit and integration tests with `pytest` + `pytest-django`

## Requirements

- Python 3.11+
- `pip`

## Minimal Django integration

### 1) Install app and middleware

```python
# settings.py
INSTALLED_APPS = [
    # ...
    "ftn_audit.apps.FtnAuditConfig",
]

MIDDLEWARE = [
    # ...
    "ftn_audit.middleware.AuditContextMiddleware",
]
```

### 2) Configure Celery task discovery

```python
# celery.py
from celery import Celery

app = Celery("service_name")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

### 3) Register formatters in each app

```python
# my_app/audit_formatters.py
from ftn_audit import register_audit_formatter, AbstractAuditLogFormatter
from .models import MyModel


@register_audit_formatter(MyModel)
class MyFormatter(AbstractAuditLogFormatter):
    def get_description(self) -> str:
        return f"Updated MyModel #{self.subject.pk}"

    def get_attributes(self):
        attrs = self.get_default_attributes()
        attrs["my.attr"] = "value"
        return attrs
```

Formatter resolution order:

1. `(raw_route + event_type)`
2. `(raw_route)`
3. `(event_type)`
4. `(default)`

`priority` is only applied inside the same specificity tier.

### 4) Recommended settings

```python
AUDIT_ENABLED = True
AUDIT_DELIVERY_MODE = "celery"  # celery | sync | noop
AUDIT_OTLP_FALLBACK = "structured_log"  # structured_log | drop
AUDIT_STRICT_FORMATTER_VALIDATION = True
AUDIT_AUTO_CONNECT_SIGNALS = True  # optional, default True
AUDIT_AUTO_DISCOVER_FORMATTERS = True  # optional, default True
AUDIT_CHANGESET_CHECK_RELATIONSHIP = True  # optional, include FK changes in changeset
```

## Migration notes

- Foreign-key auditing:
  `AUDIT_CHANGESET_CHECK_RELATIONSHIP` defaults to `True`.
  Set it to `False` only if your service explicitly wants to skip FK changes in update changesets.
- Formatter `raw_route` compatibility:
  middleware now emits canonical placeholders (`:name`).
  Update formatter `raw_route=` registrations from legacy forms (`<type:name>`, `(?P<name>...)`) to `:name`.
- Import path rename:
  `ftn_audit.jobs` was renamed to `ftn_audit.tasks`.
  Update imports, e.g. `from ftn_audit.tasks import emit_audit_log_task`.

## Error handling and safeguards

- Audit code should never break request execution:
  all middleware/receiver/strategy exceptions are caught and logged.
- Enqueue failures are logged and dropped.
- OTLP emission failures in Celery use bounded retries.
- OTLP enqueue is registered via `transaction.on_commit`, so events are emitted only after commit.
- Signal handlers ignore `raw=True` fixture loads to avoid spurious audit events.
- Changesets are filtered by `update_fields` when present, so only persisted fields are audited.
- M2M payload safety:
  PK sets are capped (`M2M_PK_SET_MAX`) to avoid oversized OTLP payloads.
- Celery audit task uses `ignore_result=True` to avoid unnecessary result-backend writes.

## Known limitations

- Django bulk operations bypass per-instance signals (`bulk_create`, `bulk_update`, queryset `update`, queryset `delete`).
  If needed, add explicit auditing at service-layer boundaries.
- Reverse-side M2M modifications (`reverse=True`) are not audited by default.
  This can be extended with explicit configuration if your domain needs it.
- One-to-many collection semantics should be expressed through child create/update/delete formatters (FK changes).
  There is no dedicated O2M signal registry yet.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[test]
```

## Makefile workflow

Bootstrap environment:

```bash
make bootstrap
```

Run tests:

```bash
make test
```

Shortcuts:

- `make test-unit`
- `make test-integration`
- `make docker-build`
- `make docker-test`

## Test commands

Run all tests:

```bash
pytest -q
```

Run focused unit tests:

```bash
pytest -q tests/test_middleware.py tests/test_strategy.py tests/test_receiver_unit.py tests/test_tasks.py
```

Run integration tests:

```bash
pytest -q tests/test_receiver_integration.py
```

## Minimum test coverage checklist

Shared library tests cover:

- autodiscovery imports both `audit_formatters.py` modules and `audit_formatters` packages
- middleware canonical `raw_route`
- registry selection (`raw_route` match -> default -> generic)
- M2M receiver firing only for allowlisted collections
- commit safety (`rollback` prevents enqueue)
- enqueue failure (`log + drop`)
- OTLP task retries are bounded

Microservice-level expectations:

- formatter unit tests for key routes
- startup integration test verifies registrations are loaded into registry

## Acceptance criteria status

- No explicit audit calls in business logic: yes (signal + middleware driven).
- Audit events include `raw_route` and user metadata when available: yes.
- Formatter selection is based on HTTP verb + route template: yes (`raw_route = METHOD|/template`).
- M2M relations are audited only when allowlisted (`@register_audit_collection`): yes.
- OTLP emission happens only after commit: yes (`transaction.on_commit`).
- Audit failures never break the request path: yes (exceptions are swallowed and logged).

## Notes

- Tests use minimal Django settings from `tests/settings.py`.
- Test app is under `tests/test_app`.
- OTLP network emission is mocked in tests (`emit_audit_log_task.delay`).

## Docker

Build image:

```bash
docker compose build
```

Run tests in container:

```bash
docker compose run --rm test
```
