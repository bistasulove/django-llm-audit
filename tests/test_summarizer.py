"""Tests for llm_audit.summarizer (M2).

The LLM is an I/O dependency, so we mock it — not the data (CLAUDE.md §11). A tiny local
fake records every ``.complete`` call; this is enough to prove the map-reduce branching.
The full reusable MockBackend arrives in M5.
"""

from llm_audit import summarizer
from llm_audit.prompts import META_SYSTEM_PROMPT, SYSTEM_PROMPT


class FakeBackend:
    """Records each call and returns a fixed reply."""

    def __init__(self, reply="SUMMARY"):
        self.reply = reply
        self.calls = []  # list of (prompt, system) tuples, in call order

    def complete(self, prompt, system=None):
        self.calls.append((prompt, system))
        return self.reply


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
