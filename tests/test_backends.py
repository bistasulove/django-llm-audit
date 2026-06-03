"""Tests for llm_audit.backends. Full coverage arrives in M5/M6."""

from llm_audit.backends.base import BaseLLMBackend
from llm_audit.exceptions import LLMAuditError, LLMBackendError


def test_base_backend_is_abstract():
    import pytest

    with pytest.raises(TypeError):
        BaseLLMBackend()  # cannot instantiate an ABC with abstract methods


def test_backend_error_hierarchy():
    assert issubclass(LLMBackendError, LLMAuditError)
