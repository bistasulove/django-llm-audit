"""Tests for the ``audit_model`` management command.

Two layers here:

* **Unit** — ``_resolve_stream`` is a pure staticmethod, so we test the streaming policy
  directly with no DB or backend.
* **Integration** (M6) — ``call_command`` drives the whole pipeline end to end against a real
  ``testapp.Order`` queryset, with only the LLM faked via :class:`MockBackend` (CLAUDE.md §11:
  mock the LLM, not the data). These are the command tests deferred since M1 — they needed a
  resolvable model with records (now ``testapp.Order``) and an offline backend (``MockBackend``).

The default ``--app/--model`` is ``store.Order``, absent from the test settings, so the
no-args smoke test still exercises clean error handling without reaching any backend.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from llm_audit.management.commands.audit_model import Command


def _run(**kwargs):
    """Call ``audit_model`` against ``testapp.Order``, capturing stdout into a buffer.

    ``call_command`` accepts a ``stdout`` stream; returning its contents lets tests assert on
    what the user would see. ``--no-stream`` keeps prose buffered so the output is a single
    block rather than token-by-token writes.
    """
    from io import StringIO

    out = StringIO()
    call_command("audit_model", app="testapp", model="Order", stdout=out, **kwargs)
    return out.getvalue()


def test_audit_model_raises_clean_error_for_unknown_model():
    # The command's default target is store.Order, which is absent from the test
    # settings — so resolution should fail with a CommandError, not a traceback, and
    # without reaching the Anthropic backend.
    with pytest.raises(CommandError, match="Could not resolve model"):
        call_command("audit_model")


# ---- End-to-end via call_command + MockBackend (M6) --------------------------------------


def test_prose_run_produces_a_summary(seeded_orders, use_mock_backend):
    # The default text path: resolve -> .values() -> chunk -> summarize -> stdout. MockBackend
    # returns deterministic prose, so we can assert its known reply made it through unchanged.
    output = _run(stream=False)
    assert "Auditing 5 Order record(s)" in output
    assert "Mock summary" in output


def test_streaming_prose_writes_tokens_then_tally(seeded_orders, use_mock_backend):
    # The default interactive path streams: MockBackend.stream() yields the prose word by
    # word, which the command writes piece by piece and follows with a token-count tally.
    output = _run(stream=True)
    assert "Mock summary" in output  # the streamed pieces reassembled into the full reply
    assert "tokens received" in output  # the end-of-stream tally line


def test_limit_caps_the_record_count(seeded_orders, use_mock_backend):
    # --limit is the safety cap on how many rows are pulled (ADR-005). With 5 seeded rows,
    # --limit 2 should audit exactly 2.
    output = _run(limit=2, stream=False)
    assert "Auditing 2 Order record(s)" in output


def test_empty_queryset_warns_and_skips_the_llm(db, use_mock_backend):
    # No rows seeded: the command should short-circuit with a friendly warning and never call
    # the backend (the "Auditing N record(s)" banner only prints once there is data).
    output = _run(stream=False)
    assert "Nothing to audit" in output
    assert "Auditing" not in output


def test_format_json_emits_valid_report_json(seeded_orders, use_mock_backend):
    # The structured path: MockBackend returns schema-valid JSON, which summarize() validates
    # into a SummaryReport and the formatter renders. The emitted block must parse and carry
    # the metadata we inject ourselves (model_name/record_count), not values from the LLM.
    output = _run(format="json")
    payload = json.loads(_extract_json(output))
    assert payload["model_name"] == "Order"
    assert payload["record_count"] == 5
    assert "headline" in payload and "anomalies" in payload


def test_format_markdown_to_file_writes_report(seeded_orders, use_mock_backend, tmp_path):
    # --output writes the rendered report to disk and prints a success notice instead of the
    # body. tmp_path is pytest's per-test temp directory.
    target = tmp_path / "report.md"
    output = _run(format="markdown", output=str(target))
    assert f"Report written to {target}" in output
    assert target.exists()
    assert target.read_text().strip()  # non-empty markdown


def test_backend_override_selects_mock(seeded_orders, settings):
    # Configure a backend that would fail (no key), then prove --backend overrides it for the
    # run: pointing at MockBackend lets the command complete offline.
    settings.LLM_AUDIT = {"BACKEND": "anthropic", "API_KEY": None}
    output = _run(stream=False, backend="llm_audit.backends.mock.MockBackend")
    assert "Auditing 5 Order record(s)" in output


def _extract_json(output: str) -> str:
    """Pull the JSON object out of command output that also contains notice lines."""
    start = output.index("{")
    end = output.rindex("}") + 1
    return output[start:end]


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
