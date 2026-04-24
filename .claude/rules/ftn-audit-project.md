# ftn-audit — Project Rules

## Tech Stack

- **Language:** Python 3.11+
- **Framework:** Django >= 4.2, Django REST Framework
- **Task Queue:** Celery >= 5.3
- **Telemetry:** OpenTelemetry API/SDK >= 1.20, < 2.0
- **Dirty Tracking:** django-dirtyfields >= 1.9
- **Build:** setuptools, src layout
- **Testing:** pytest >= 8.2, pytest-django >= 4.8

## Development Commands

| Task | Command |
|------|---------|
| Install (dev) | `pip install -e ".[test]"` |
| Tests | `pytest -q` |
| Tests + coverage | `pytest --cov=src/ftn_audit --cov-fail-under=80` |
| Single test | `pytest tests/test_receiver_unit.py -q` |

## Directory Layout

- `src/ftn_audit/` — library source (installed as `ftn_audit` package)
- `tests/` — pytest suite with Django test app (`tests/test_app/`)
- `tests/settings.py` — minimal Django config (SQLite in-memory)
- `tests/conftest.py` — sets `DJANGO_SETTINGS_MODULE`

## Test Infrastructure

Tests use a dedicated Django app (`tests.test_app`) with models:
- `AuditedThing` — basic auditable model with DirtyFieldsMixin
- `Tag` — M2M target model
- `AuditedBasket` — model with M2M field for collection audit tests

All DB tests use `@pytest.mark.django_db(transaction=True)` because audit emission defers to `transaction.on_commit`.

## Key Conventions

- All magic strings centralized in `constants.py` — import from there, never hardcode
- Module-level `FormatterEmitter` instances for centralized error handling
- `contextvars` for request/context storage (ASGI-safe, no thread-local)
- Strategy singleton with double-checked locking (`get_audit_strategy()`)
