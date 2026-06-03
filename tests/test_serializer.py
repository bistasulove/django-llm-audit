"""Tests for llm_audit.serializer. Full coverage arrives in M2/M6."""

import pytest

from llm_audit import serializer


def test_serialize_records_is_a_placeholder():
    with pytest.raises(NotImplementedError):
        serializer.serialize_records()
