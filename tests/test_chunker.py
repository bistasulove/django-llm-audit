"""Tests for llm_audit.chunker (M2). Pure functions — no Django, no API."""

import pytest

from llm_audit.chunker import chunk_records, estimate_tokens
from llm_audit.exceptions import ChunkingError
from llm_audit.serializer import serialize_records


def _record(size: int) -> dict:
    """A record whose compact-JSON token estimate is roughly ``size // 4``."""
    return {"v": "x" * size}


def _chunk_tokens(chunk: list[dict]) -> int:
    return estimate_tokens(serialize_records(chunk, indent=None))


def test_estimate_tokens_is_four_chars_per_token():
    assert estimate_tokens("a" * 40) == 10
    assert estimate_tokens("") == 0


def test_empty_input_yields_no_chunks():
    assert chunk_records([], token_threshold=100) == []


def test_everything_under_threshold_is_one_chunk():
    records = [{"id": 1}, {"id": 2}, {"id": 3}]
    chunks = chunk_records(records, token_threshold=10_000)
    assert chunks == [records]


def test_splits_into_multiple_chunks_when_over_threshold():
    # Each record is ~25 tokens; a 60-token threshold fits two per chunk, not three.
    records = [_record(100) for _ in range(5)]
    chunks = chunk_records(records, token_threshold=60)
    assert len(chunks) > 1
    # Every multi-record chunk stays under the threshold...
    for chunk in chunks:
        if len(chunk) > 1:
            assert _chunk_tokens(chunk) <= 60


def test_no_records_lost_and_order_preserved():
    records = [{"id": i} for i in range(10)]
    chunks = chunk_records(records, token_threshold=20)
    flattened = [r for chunk in chunks for r in chunk]
    assert flattened == records


def test_oversized_single_record_becomes_its_own_chunk():
    # One record alone exceeds the threshold: it must still come through, alone, rather
    # than fail the run or vanish.
    records = [_record(20), _record(4000), _record(20)]
    chunks = chunk_records(records, token_threshold=50)
    oversized = [c for c in chunks if len(c) == 1 and _chunk_tokens(c) > 50]
    assert len(oversized) == 1
    assert oversized[0][0] == _record(4000)
    # And nothing was dropped.
    assert sum(len(c) for c in chunks) == 3


def test_non_positive_threshold_raises_chunking_error():
    with pytest.raises(ChunkingError):
        chunk_records([{"id": 1}], token_threshold=0)
    with pytest.raises(ChunkingError):
        chunk_records([{"id": 1}], token_threshold=-5)
