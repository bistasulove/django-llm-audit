"""Tests for the audit_model command. Full coverage (via MockBackend) arrives in M6.

The test settings deliberately have no ``store`` app, so these M1 smoke tests exercise
the command's registration and model-resolution path without ever calling the LLM.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_audit_model_raises_clean_error_for_unknown_model():
    # The command's default target is store.Order, which is absent from the test
    # settings — so resolution should fail with a CommandError, not a traceback, and
    # without reaching the Anthropic backend.
    with pytest.raises(CommandError, match="Could not resolve model"):
        call_command("audit_model")


def test_conf_defaults():
    from llm_audit.conf import audit_settings

    assert audit_settings.MAX_TOKENS == 1024
    assert audit_settings.DEFAULT_RECORD_LIMIT == 50
