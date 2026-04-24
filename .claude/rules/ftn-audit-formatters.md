# ftn-audit — Formatter Authoring

## Writing a Custom Formatter

```python
from ftn_audit import register_audit_formatter, AbstractAuditLogFormatter
from myapp.models import Order

@register_audit_formatter(Order)
class OrderFormatter(AbstractAuditLogFormatter):
    def get_description(self) -> str:
        return f"Order #{self.subject.pk} {self.event_type}"

    def get_attributes(self):
        return self.merge_attributes({
            "order.total": str(self.subject.total),
            "order.status": self.subject.status,
        })
```

## Key Rules

- **Inherit `AbstractAuditLogFormatter`** — provides `get_default_attributes()`, `merge_attributes()`, `build_change_details()`, `get_user_info()`
- **Use `merge_attributes(extra)`** to extend defaults — never build attrs from scratch
- **Use `get_default_attributes()`** if overriding `get_attributes()` without `merge_attributes()`
- **Prefer `merge_attributes(extra)` or `get_default_attributes()`** over `super().get_attributes()` — clearer intent and avoids confusion with the `IAuditLogFormatter` protocol
- `IGNORED_FIELDS` (`created`, `modified`, `created_at`, `updated_at`, `created_by`, `updated_by`) are auto-filtered from changesets — exact name matches only, not wildcards

## Route-Scoped Formatters

```python
@register_audit_formatter(Order, raw_route="PUT|/api/v1/orders/:pk")
class OrderUpdateViaAPI(AbstractAuditLogFormatter):
    ...
```

**Route format:** `METHOD|/path/with/:param` — params use `:name` form (not `<type:name>` or `(?P<name>...)`).

## M2M Collection Auditing

Opt-in per model+field in `audit_formatters.py`:

```python
from ftn_audit import register_audit_collection
from myapp.models import Order

register_audit_collection(Order, "tags")
```

M2M events use `GenericCollectionUpdateFormatter`. `pk_set` is capped at 500 items (`M2M_PK_SET_MAX`).

## Autodiscovery

`FtnAuditConfig.ready()` imports `<app>.audit_formatters` from every app in `INSTALLED_APPS`. Place formatters in `myapp/audit_formatters.py`.
