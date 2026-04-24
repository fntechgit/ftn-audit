# ftn-audit — Troubleshooting

## Audit Events Not Appearing

| Symptom | Cause | Fix |
|---------|-------|-----|
| No events at all | `AUDIT_ENABLED = False` or `AUDIT_DELIVERY_MODE = "noop"` | Check Django settings |
| Events for some models only | Model not registered in `AuditFormattersRegistry` | Add `@register_audit_formatter(Model)` in `audit_formatters.py` |
| Events fire but Celery task fails | `emit_audit_log_task` not discovered | Ensure `app.autodiscover_tasks()` in Celery config and `ftn_audit` in `INSTALLED_APPS` |
| Events fire but callback never runs | `save()` outside `transaction.atomic()` | `transaction.on_commit` requires an active transaction |
| Update events silently dropped | No dirty fields detected | Verify `DirtyFieldsMixin` is **FIRST** in MRO |
| M2M events not firing | Collection not registered | Call `register_audit_collection(Model, "field_name")` |

## Context / Actor Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `user_id` is `None` | Middleware runs before auth (DRF token) | Expected — receivers hydrate from `request.auth` or `request.user` |
| Context is `None` entirely | Middleware not installed or not FIRST | Add `AuditContextMiddleware` as FIRST in `MIDDLEWARE` |
| `raw_route` is `None` | `resolver_match` unavailable | Signal fired outside HTTP request (management command, Celery task) |
| Wrong user on audit event | `contextvars` leaking across requests | Check ASGI compatibility — middleware cleans up in `finally` block |

## Formatter Errors

| Symptom | Cause | Fix |
|---------|-------|-----|
| `TypeError: Invalid audit formatter instance` | Formatter doesn't satisfy `IAuditLogFormatter` protocol | Implement `get_description()` and `get_attributes()` methods |
| `NotImplementedError` in logs | Formatter inherits `AbstractAuditLogFormatter` but doesn't override `get_description()` | Override `get_description()` to return a string |
| `TypeError` swallowed silently | `AUDIT_STRICT_FORMATTER_VALIDATION = False` | Set to `True` during development to surface errors |

## Celery Task Failures

The `emit_audit_log_task` retries up to 2 times with 5-second delays (`DEFAULT_TASK_MAX_RETRIES`, `DEFAULT_TASK_RETRY_DELAY_SECONDS`).

| Log Message | Meaning |
|-------------|---------|
| `Unable to enqueue task 'ftn_audit.emit_audit_log'` | Celery broker unreachable or task not registered |
| `Unable to register audit on_commit callback` | Transaction state issue — event dropped |
| `pre_save changeset capture failed` | `DirtyFieldsMixin` missing or model state issue |

## Debug Logging

Enable audit loggers to trace the full flow:

```python
LOGGING = {
    "loggers": {
        "audit": {"level": "DEBUG", "handlers": ["console"]},
        "audit.otlp": {"level": "DEBUG", "handlers": ["console"]},
        "audit.m2m": {"level": "DEBUG", "handlers": ["console"]},
    }
}
```
