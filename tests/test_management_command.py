"""Tests for the audit_model command. Full coverage (via MockBackend) arrives in M6.

The test settings deliberately have no ``store`` app, so these M1 smoke tests exercise
the command's registration and model-resolution path without ever calling the LLM.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from llm_audit.management.commands.audit_model import Command


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


# ---- _resolve_stream: the "stream whenever it can" policy ---------------------------------
#
# explicit_stream is tri-state: True (--stream), False (--no-stream), None (neither given).


def test_text_to_terminal_streams_by_default():
    # The new default: interactive prose streams without any flag.
    assert Command._resolve_stream("text", None, None) == (True, False)


def test_text_no_stream_opts_out():
    assert Command._resolve_stream("text", None, False) == (False, False)


def test_text_explicit_stream_streams():
    assert Command._resolve_stream("text", None, True) == (True, False)


@pytest.mark.parametrize("fmt", ["json", "markdown"])
def test_structured_never_streams(fmt):
    # No flag: buffer silently (no warning — the user didn't ask to stream).
    assert Command._resolve_stream(fmt, None, None) == (False, False)


@pytest.mark.parametrize("fmt", ["json", "markdown"])
def test_structured_warns_only_on_explicit_stream(fmt):
    # --stream + a structured format: buffer, but warn that the flag was ignored.
    assert Command._resolve_stream(fmt, None, True) == (False, True)


def test_file_output_buffers_without_warning():
    # A file has no cursor to animate, so even default text buffers — and silently.
    assert Command._resolve_stream("text", "report.md", None) == (False, False)
    assert Command._resolve_stream("text", "report.md", True) == (False, False)
