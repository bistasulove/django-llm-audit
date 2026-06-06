"""Shared pytest fixtures for the django-llm-audit test suite.

``DJANGO_SETTINGS_MODULE`` is set via ``pyproject.toml`` (``tests.settings``).

M5 adds the ``mock_backend`` fixture, wrapping the shipped
:class:`~llm_audit.backends.mock.MockBackend`. It is the offline, deterministic backend the
command tests in M6 inject so they never need an API key.

M6 adds two fixtures the command/serializer integration tests rely on:

* ``seeded_orders`` — a handful of real ``testapp.Order`` rows, so the command can resolve a
  model and pull records exactly as it would in production. We seed the *data* for real; only
  the LLM is faked (CLAUDE.md §11).
* ``use_mock_backend`` — points ``LLM_AUDIT["BACKEND"]`` at :class:`MockBackend` for the test,
  so ``call_command`` runs the full pipeline offline and deterministically.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from llm_audit.backends.mock import MockBackend
from tests.testapp.models import Order


@pytest.fixture
def mock_backend():
    """A fresh, deterministic, offline backend instance for each test."""
    return MockBackend()


@pytest.fixture
def use_mock_backend(settings):
    """Force the configured backend to the offline MockBackend for the duration of a test.

    Uses pytest-django's ``settings`` fixture, which restores the original value afterwards.
    A flat ``LLM_AUDIT`` (single implicit backend) is all the command needs here.
    """
    settings.LLM_AUDIT = {"BACKEND": "llm_audit.backends.mock.MockBackend"}


# A fixed timestamp keeps serialized output deterministic across runs.
_SEED_TS = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def seeded_orders(db):
    """Create and return a small set of real Order rows.

    ``db`` is pytest-django's database-access fixture; requesting it is what lets a test
    touch the ORM. The data deliberately includes a couple of statuses and Decimal totals so
    serialization and any field-aware logic see realistic shapes.
    """
    orders = [
        Order.objects.create(
            status=status,
            total=Decimal(total),
            customer_email=f"buyer{i}@example.com",
            created_at=_SEED_TS,
        )
        for i, (status, total) in enumerate(
            [
                ("paid", "19.99"),
                ("paid", "120.00"),
                ("refunded", "45.50"),
                ("pending", "8.00"),
                ("shipped", "230.75"),
            ]
        )
    ]
    return orders
