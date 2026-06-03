"""Tests for llm_audit.summarizer. Full coverage arrives in M6 (via MockBackend)."""

import pytest

from llm_audit import summarizer


def test_summarize_is_a_placeholder():
    with pytest.raises(NotImplementedError):
        summarizer.summarize()
