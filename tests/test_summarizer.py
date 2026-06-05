"""Tests for llm_audit.summarizer (M2).

The LLM is an I/O dependency, so we mock it — not the data (CLAUDE.md §11). A tiny local
fake records every ``.complete`` call; this is enough to prove the map-reduce branching.
The full reusable MockBackend arrives in M5.
"""

import json

import pytest

from llm_audit import summarizer
from llm_audit.exceptions import StructuredOutputError
from llm_audit.prompts import (
    META_SYSTEM_PROMPT,
    STRUCTURED_META_SYSTEM_PROMPT,
    STRUCTURED_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
)
from llm_audit.schemas.report import SummaryReport

VALID_BODY_JSON = json.dumps(
    {
        "headline": "H",
        "patterns": ["a", "b"],
        "anomalies": [{"field": "status", "description": "d", "severity": "high"}],
        "assessment": "overall fine",
    }
)


class FakeBackend:
    """Records each call and returns a fixed reply.

    Tracks blocking ``complete`` calls and streaming ``stream`` calls separately so a
    test can assert *which* path the summarizer used for each step.
    """

    def __init__(self, reply="SUMMARY", stream_pieces=("TWO ", "PART")):
        self.reply = reply
        self.stream_pieces = stream_pieces
        self.calls = []  # (prompt, system) tuples from complete(), in call order
        self.stream_calls = []  # (prompt, system) tuples from stream(), in call order

    def complete(self, prompt, system=None):
        self.calls.append((prompt, system))
        return self.reply

    def stream(self, prompt, system=None):
        self.stream_calls.append((prompt, system))
        yield from self.stream_pieces


class StructuredBackend:
    """Fake for the structured path.

    A *structured* (terminal) call is recognised by the JSON-output rule baked into its
    system prompt; those calls return the next queued JSON reply. Any other call is a prose
    map step and returns a fixed partial summary. This lets one fake serve both the map
    (prose) and reduce (JSON) steps of a multi-chunk structured run.
    """

    def __init__(self, structured_replies, prose="PARTIAL SUMMARY"):
        self.structured_replies = list(structured_replies)
        self.prose = prose
        self.calls = []  # (prompt, system) in order

    def complete(self, prompt, system=None):
        self.calls.append((prompt, system))
        if system and "single JSON object" in system:
            return self.structured_replies.pop(0)
        return self.prose


def _record(size: int) -> dict:
    return {"v": "x" * size}


def test_single_chunk_makes_one_call_and_returns_it():
    backend = FakeBackend(reply="THE SUMMARY")
    records = [{"id": 1}, {"id": 2}]

    result = summarizer.summarize(
        records, model_name="Order", backend=backend, token_threshold=10_000
    )

    assert result == "THE SUMMARY"
    assert len(backend.calls) == 1
    # A single chunk uses the audit (map) prompt, never the meta (reduce) prompt.
    assert backend.calls[0][1] == SYSTEM_PROMPT


def test_many_chunks_map_then_reduce():
    backend = FakeBackend()
    # ~25 tokens each, threshold 60 -> multiple chunks, forcing the reduce step.
    records = [_record(100) for _ in range(5)]

    summarizer.summarize(records, model_name="Order", backend=backend, token_threshold=60)

    systems = [system for _, system in backend.calls]
    # Last call is the reduce step; every earlier call is a map step.
    assert systems[-1] == META_SYSTEM_PROMPT
    assert all(system == SYSTEM_PROMPT for system in systems[:-1])
    # One map call per chunk, plus exactly one reduce call.
    assert systems.count(META_SYSTEM_PROMPT) == 1
    assert systems.count(SYSTEM_PROMPT) >= 2


def test_single_chunk_streams_the_terminal_call():
    backend = FakeBackend(stream_pieces=("ONE ", "TWO"))
    records = [{"id": 1}, {"id": 2}]

    result = summarizer.summarize(
        records, model_name="Order", backend=backend, token_threshold=10_000, stream=True
    )

    # stream=True returns a generator; consuming it yields the streamed pieces in order.
    assert "".join(result) == "ONE TWO"
    # The terminal call streamed; nothing went through the blocking complete() path.
    assert len(backend.stream_calls) == 1
    assert len(backend.calls) == 0
    assert backend.stream_calls[0][1] == SYSTEM_PROMPT


def test_multi_chunk_streams_only_the_reduce_call():
    backend = FakeBackend()
    # ~25 tokens each, threshold 60 -> multiple chunks, forcing a map + reduce run.
    records = [_record(100) for _ in range(5)]

    result = summarizer.summarize(
        records, model_name="Order", backend=backend, token_threshold=60, stream=True
    )
    list(result)  # consume the terminal stream

    # The map steps must stay blocking (their full text feeds the reduce prompt), so they
    # use complete(); only the final reduce call streams.
    assert len(backend.stream_calls) == 1
    assert backend.stream_calls[0][1] == META_SYSTEM_PROMPT
    assert len(backend.calls) >= 2
    assert all(system == SYSTEM_PROMPT for _, system in backend.calls)


def test_notify_receives_progress_for_multi_chunk_run():
    backend = FakeBackend()
    messages = []
    records = [_record(100) for _ in range(5)]

    summarizer.summarize(
        records,
        model_name="Order",
        backend=backend,
        token_threshold=60,
        notify=messages.append,
    )

    assert any("chunk" in m.lower() for m in messages)


def test_oversized_record_warns_via_notify():
    backend = FakeBackend()
    messages = []
    records = [_record(4000)]  # one record, far over the threshold

    summarizer.summarize(
        records,
        model_name="Order",
        backend=backend,
        token_threshold=50,
        notify=messages.append,
    )

    assert any("exceeds" in m.lower() for m in messages)


# ---- Structured output (M4) ----------------------------------------------------------


def test_structured_single_chunk_returns_validated_report():
    backend = StructuredBackend([VALID_BODY_JSON])
    records = [{"id": 1}, {"id": 2}]

    report = summarizer.summarize(
        records, model_name="Order", backend=backend, token_threshold=10_000, structured=True
    )

    assert isinstance(report, SummaryReport)
    # Metadata is injected by us, not taken from the LLM body.
    assert report.model_name == "Order"
    assert report.record_count == 2
    # Analytical fields come from the validated body.
    assert report.headline == "H"
    assert report.anomalies[0].severity == "high"
    # One structured terminal call, no reduce.
    assert len(backend.calls) == 1
    assert backend.calls[0][1] == STRUCTURED_SYSTEM_PROMPT


def test_structured_retries_then_succeeds_on_valid_json():
    # First reply is unparseable; second is good. One retry should recover.
    backend = StructuredBackend(["not json at all", VALID_BODY_JSON])
    messages = []
    records = [{"id": 1}]

    report = summarizer.summarize(
        records,
        model_name="Order",
        backend=backend,
        token_threshold=10_000,
        structured=True,
        notify=messages.append,
    )

    assert isinstance(report, SummaryReport)
    assert len(backend.calls) == 2  # initial attempt + one retry
    assert any("retry" in m.lower() for m in messages)


def test_structured_retries_on_schema_violation():
    # Valid JSON but a severity outside the enum -> ValidationError -> retry, then recover.
    bad_schema = json.dumps(
        {
            "headline": "H",
            "patterns": ["a"],
            "anomalies": [{"field": "x", "description": "d", "severity": "critical"}],
            "assessment": "z",
        }
    )
    backend = StructuredBackend([bad_schema, VALID_BODY_JSON])
    records = [{"id": 1}]

    report = summarizer.summarize(
        records, model_name="Order", backend=backend, token_threshold=10_000, structured=True
    )

    assert isinstance(report, SummaryReport)
    assert len(backend.calls) == 2


def test_structured_raises_after_exhausting_retries():
    # Always-bad output: initial attempt + max_retries, then give up.
    backend = StructuredBackend(["nope", "still nope", "nope again", "and again"])
    records = [{"id": 1}]

    with pytest.raises(StructuredOutputError):
        summarizer.summarize(
            records,
            model_name="Order",
            backend=backend,
            token_threshold=10_000,
            structured=True,
            max_retries=2,
        )

    assert len(backend.calls) == 3  # 1 + 2 retries


def test_structured_multi_chunk_maps_prose_then_reduces_to_json():
    backend = StructuredBackend([VALID_BODY_JSON])
    records = [_record(100) for _ in range(5)]  # forces multiple chunks at threshold 60

    report = summarizer.summarize(
        records, model_name="Order", backend=backend, token_threshold=60, structured=True
    )

    assert isinstance(report, SummaryReport)
    assert report.record_count == 5
    systems = [system for _, system in backend.calls]
    # Exactly one structured (reduce) call; all earlier calls are prose map steps.
    assert systems[-1] == STRUCTURED_META_SYSTEM_PROMPT
    assert all(system == SYSTEM_PROMPT for system in systems[:-1])
    assert systems.count(STRUCTURED_META_SYSTEM_PROMPT) == 1
