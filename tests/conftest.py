"""Shared pytest fixtures for the django-llm-audit test suite.

``DJANGO_SETTINGS_MODULE`` is set via ``pyproject.toml`` (``tests.settings``).

M5 adds the ``mock_backend`` fixture, wrapping the shipped
:class:`~llm_audit.backends.mock.MockBackend`. It is the offline, deterministic backend the
command tests in M6 will inject so they never need an API key.
"""

import pytest

from llm_audit.backends.mock import MockBackend


@pytest.fixture
def mock_backend():
    """A fresh, deterministic, offline backend instance for each test."""
    return MockBackend()
