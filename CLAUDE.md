# ftn-audit — Foxtrot November Shared Audit Logging Library

## What This Is

Shared Django/DRF audit logging library used by all Sponsor Services microservices. Automatically captures create/update/delete events on registered models via Django signals and emits them as OpenTelemetry log records through Celery.

Originally called `fntech-audit` in the SDS — renamed to `ftn-audit` (Python module: `ftn_audit`) in March 2026.

## Package Structure

```
ftn-audit/
  pyproject.toml            # pip-installable, src layout
  src/ftn_audit/
    __init__.py             # Public API exports
    apps.py                 # FtnAuditConfig — connects signals + autodiscovers formatters
    autodiscover.py         # Imports <app>.audit_formatters from all INSTALLED_APPS
    context.py              # AuditContext frozen dataclass (user, route, request metadata)
    context_storage.py      # contextvars-based storage (ASGI-safe)
    middleware.py            # AuditContextMiddleware — populates context per request
    changeset.py            # build_changeset() using django-dirtyfields
    serialization.py        # make_json_safe() recursive converter for Celery payloads
    registry.py             # AuditFormattersRegistry + @register_audit_formatter
    collections_registry.py # AuditCollectionsRegistry + register_audit_collection()
    base_formatter.py       # IAuditLogFormatter protocol + AbstractAuditLogFormatter
    generic_formatters.py   # Generic{Creation,Update,Deletion,CollectionUpdate}Formatter
    formatter_factory.py    # AuditLogFormatterFactory.make() — registry → generic fallback
    receiver.py             # pre_save/post_save/post_delete signal receivers
    m2m_receiver.py         # m2m_changed signal receiver for collection auditing
    strategy.py             # NoopAuditStrategy + OtlpAuditStrategy + get_audit_strategy()
    jobs.py                 # emit_audit_log_task Celery shared_task (max_retries=2)
    py.typed                # PEP 561 marker
```

## How It Works

1. `AuditContextMiddleware` captures user/request info into a `ContextVar` on every request
2. `pre_save` receiver captures dirty-field changeset before DB write
3. `post_save` / `post_delete` / `m2m_changed` receivers format audit events
4. Formatter is resolved: registry lookup (model + route + event) → generic fallback
5. `OtlpAuditStrategy` defers emission to `transaction.on_commit` → Celery task
6. Celery task delivers via OpenTelemetry Logs API with bounded retries

## Key Design Rules

- **DirtyFieldsMixin must be FIRST in MRO** on base concrete models in consuming services
- **Only add to base classes** — child models (e.g., StripePayment extends Payment) inherit it
- **Metadata models are NOT audited** — they're read replicas synced via RabbitMQ
- **Formatter priority:** exact route+event → route-only → event-only → model default → generic
- **M2M auditing is opt-in** via `register_audit_collection(Model, "field_name")`
- **Never break the request** — all signal handlers wrapped in try/except

## Consuming Services

Each service needs:
1. `ftn_audit.apps.FtnAuditConfig` as FIRST entry in `INSTALLED_APPS`
2. `ftn_audit.middleware.AuditContextMiddleware` as FIRST entry in `MIDDLEWARE`
3. `AUDIT_ENABLED = os.getenv('AUDIT_ENABLED', 'true').lower() == 'true'`
4. `audit_formatters.py` module(s) with `@register_audit_formatter` decorators
5. `DirtyFieldsMixin` on auditable models
6. `django-dirtyfields==1.9.6`, `opentelemetry-api==1.29.0`, `opentelemetry-sdk==1.29.0` in requirements
7. Celery worker running + broker configured
8. Audit loggers: `audit`, `audit.otlp`, `audit.m2m`

## Dependencies

- Django >= 4.2
- celery >= 5.3
- django-dirtyfields >= 1.9
- opentelemetry-api >= 1.20
- opentelemetry-sdk >= 1.20

## SDS Gaps Fixed

- Missing NoopAuditStrategy → implemented
- Syntax error in get_audit_strategy() → fixed
- M2M post_clear pk_set=None crash → guarded
- Mutable class-level registry state → reset() classmethods
- Non-serializable changeset values → make_json_safe()
- trace_id never populated → _get_trace_id() from OTel span
- No fallback for failed emissions → logger.error after max retries

## ClickUp

Task list: https://app.clickup.com/9014802374/v/l/li/901414430871
