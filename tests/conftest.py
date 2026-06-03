"""Shared pytest fixtures for the django-llm-audit test suite.

Real fixtures (``mock_backend``, ``seeded_db``, etc.) are fleshed out in milestone M6.
For now this file ensures Django is configured; ``DJANGO_SETTINGS_MODULE`` is set via
``pyproject.toml`` (``tests.settings``).
"""
