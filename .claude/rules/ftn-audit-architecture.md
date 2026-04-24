# ftn-audit — Architecture & Settings

## Signal Flow

```
Request -> AuditContextMiddleware.process_view() -> set context via contextvars
         -> pre_save: capture changeset (dirty fields)
         -> post_save/post_delete: hydrate actor -> FormatterEmitter.emit()
            -> AuditLogFormatterFactory.make() resolves formatter
            -> OtlpAuditStrategy.emit() -> transaction.on_commit -> Celery task
               -> emit_audit_log_task -> OpenTelemetry LogRecord
```

## Actor Hydration

Middleware sets context in `process_view` (after URL resolution). If `request.user` isn't authenticated at that point (e.g., DRF token auth runs later), signal receivers call `get_current_audit_context_with_user()` which:
1. Checks `request.auth` dict (DRF token payload) for `user_id`, `user_email`, etc.
2. Falls back to `request.user` if authenticated
3. Returns context as-is if neither source has user info

## Settings Reference

All settings are read via `getattr(settings, SETTING_*, DEFAULT_*)` pattern.

| Setting | Default | Purpose |
|---------|---------|---------|
| `AUDIT_ENABLED` | `True` | Master switch — `False` activates `NoopAuditStrategy` |
| `AUDIT_DELIVERY_MODE` | `"celery"` | `"celery"` (async), `"noop"` (discard). `"sync"` logs warning and forces celery |
| `AUDIT_OTLP_FALLBACK` | `"structured_log"` | Fallback when Celery enqueue fails: `"structured_log"` or `"drop"` |
| `AUDIT_STRICT_FORMATTER_VALIDATION` | `True` | Raise `TypeError` on bad formatters vs. log and continue |
| `AUDIT_AUTO_CONNECT_SIGNALS` | `True` | Auto-connect pre_save/post_save/post_delete in `AppConfig.ready()` |
| `AUDIT_AUTO_DISCOVER_FORMATTERS` | `True` | Auto-import `audit_formatters.py` from INSTALLED_APPS |
| `AUDIT_CHANGESET_CHECK_RELATIONSHIP` | `True` | Include FK changes in update changesets |

## Formatter Resolution Priority

Registry lookup is tiered by specificity, then by `priority` within each tier:

1. Exact `(raw_route + event_type)` match
2. `raw_route`-only match
3. `event_type`-only match
4. Model default (no route, no event)
5. Generic fallback formatter

## SDS Gaps Fixed

- Missing `NoopAuditStrategy` -> implemented
- Syntax error in `get_audit_strategy()` -> fixed
- M2M `post_clear` `pk_set=None` crash -> guarded
- Mutable class-level registry state -> `reset()` classmethods
- Non-serializable changeset values -> `make_json_safe()`
- `trace_id` never populated -> `_get_trace_id()` from OTel span
- No fallback for failed emissions -> `logger.error` after max retries
