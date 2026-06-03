"""Tests for llm_audit.chunker. Full coverage arrives in M2/M6."""

from llm_audit import chunker


def test_chunk_records_is_a_placeholder():
    # The real chunking logic lands in M2; for now the stub must exist and raise.
    import pytest

    with pytest.raises(NotImplementedError):
        chunker.chunk_records()
