from __future__ import annotations

from celery import Celery

from ftn_audit.autodiscover import verify_celery_task_registered
from ftn_audit.celery import configure_celery_audit


def test_configure_celery_audit_registers_task():
    app = Celery("ftn-audit-tests")
    app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        imports=("ftn_audit.tasks",),
    )

    configure_celery_audit(app)

    assert "ftn_audit.emit_audit_log" in app.tasks


def test_verify_celery_task_registered_logs_when_missing(monkeypatch, caplog):
    class _FakeApp:
        tasks = {}

    monkeypatch.setattr("celery.current_app", _FakeApp())

    verify_celery_task_registered()

    assert "Task 'ftn_audit.emit_audit_log' not registered" in caplog.text
