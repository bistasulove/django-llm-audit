"""AppConfig for the test-only app.

This app exists solely to give the test suite a real Django model to audit, independent of
the demo project (which the plugin must never depend on — see CLAUDE.md ADR-003). Reusable
Django apps conventionally ship a tiny throwaway app like this for their own tests; DRF and
django-allauth do the same.

It has no migrations on purpose: pytest-django creates the table for migration-less apps via
``migrate --run-syncdb``, so there is nothing to keep in sync.
"""

from django.apps import AppConfig


class TestAppConfig(AppConfig):
    name = "tests.testapp"
    label = "testapp"
