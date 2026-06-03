"""Tests for the audit_model management command. Full coverage arrives in M6."""

from io import StringIO

from django.core.management import call_command


def test_audit_model_command_registers_and_runs():
    out = StringIO()
    # The stub command should run without error and announce it is not yet implemented.
    call_command("audit_model", stdout=out)
    assert "not implemented yet" in out.getvalue()


def test_conf_defaults():
    from llm_audit.conf import audit_settings

    assert audit_settings.MAX_TOKENS == 1024
    assert audit_settings.DEFAULT_RECORD_LIMIT == 50
