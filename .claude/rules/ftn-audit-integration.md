# ftn-audit — Integration Guide for Consuming Services

## Setup Checklist

1. `ftn_audit.apps.FtnAuditConfig` as **FIRST** entry in `INSTALLED_APPS`
2. `ftn_audit.middleware.AuditContextMiddleware` as **FIRST** entry in `MIDDLEWARE`
3. `AUDIT_ENABLED = os.getenv('AUDIT_ENABLED', 'true').lower() == 'true'`
4. `DirtyFieldsMixin` **FIRST in MRO** on auditable base models
5. `audit_formatters.py` module(s) with `@register_audit_formatter` decorators
6. Celery worker running + broker configured
7. `app.autodiscover_tasks()` in Celery config (discovers `ftn_audit.tasks`)

## Dependencies

```
ftn-audit                    # This library
django-dirtyfields>=1.9      # Dirty field tracking
opentelemetry-api>=1.20,<2.0 # OTel API
opentelemetry-sdk>=1.20,<2.0 # OTel SDK
```

## Logging Configuration

Configure these loggers for audit visibility:

| Logger | Purpose |
|--------|---------|
| `audit` | Main audit operations |
| `audit.otlp` | OTLP emission / Celery task |
| `audit.m2m` | M2M signal handling |

## Migration Notes

- **`ftn_audit.jobs` -> `ftn_audit.tasks`**: Update imports to `from ftn_audit.tasks import emit_audit_log_task`
- **Route format changed**: `raw_route` uses `:name` placeholders. Update formatter registrations from `<type:name>` or `(?P<name>...)` to `:name` form
- **`AUDIT_CHANGESET_CHECK_RELATIONSHIP`**: Controls FK inclusion in changesets. Default `True`. Set `False` to skip FK auditing.

## DirtyFieldsMixin Placement

```python
# CORRECT — DirtyFieldsMixin FIRST
class Payment(DirtyFieldsMixin, TimestampedModel):
    ...

# Child models inherit it — do NOT add again
class StripePayment(Payment):
    ...
```

**Do NOT add to metadata models** — they're read replicas synced via RabbitMQ, not user-mutable.
