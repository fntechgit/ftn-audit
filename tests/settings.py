"""Minimal Django settings for ftn_audit test-suite."""

SECRET_KEY = "ftn-audit-tests"
DEBUG = False
USE_TZ = True

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "dirtyfields",
    "ftn_audit.apps.FtnAuditConfig",
    "tests.test_app.apps.TestAppConfig",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

ROOT_URLCONF = "tests.urls"
MIDDLEWARE = []
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUDIT_ENABLED = True
AUDIT_AUTO_CONNECT_SIGNALS = True
AUDIT_AUTO_DISCOVER_FORMATTERS = True
