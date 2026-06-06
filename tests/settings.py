"""Minimal Django settings used by the test suite.

These settings exist solely so the plugin can be imported and exercised in isolation,
independent of the demo project. The demo project has its own settings.
"""

SECRET_KEY = "test-secret-key"

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "llm_audit",
    # A tiny test-only app providing a real model (testapp.Order) for the integration
    # tests to audit. Migration-less; pytest-django builds its table via --run-syncdb.
    "tests.testapp",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LLM_AUDIT = {
    "BACKEND": "llm_audit.backends.anthropic.AnthropicBackend",
    "API_KEY": "test-key",
}
