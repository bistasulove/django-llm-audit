"""Tests for llm_audit.backends (M5).

We test the abstraction and the factory, plus MockBackend's deterministic behaviour. We do
*not* make real Anthropic/OpenAI calls — those SDKs are external I/O, not our code (CLAUDE.md
§11). The real backends are covered here only for the parts that are ours: that they conform
to the interface and that they reject a missing API key.
"""

import json

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from llm_audit.backends import get_backend
from llm_audit.backends.anthropic import AnthropicBackend
from llm_audit.backends.base import BaseLLMBackend
from llm_audit.backends.mock import MockBackend
from llm_audit.backends.openai import OpenAIBackend
from llm_audit.exceptions import LLMAuditError, LLMBackendError
from llm_audit.prompts import STRUCTURED_SYSTEM_PROMPT, SYSTEM_PROMPT
from llm_audit.schemas.report import ReportBody

# ---- The abstraction ----------------------------------------------------------------------


def test_base_backend_is_abstract():
    with pytest.raises(TypeError):
        BaseLLMBackend()  # cannot instantiate an ABC with abstract methods


def test_backend_error_hierarchy():
    assert issubclass(LLMBackendError, LLMAuditError)


@pytest.mark.parametrize("backend_class", [AnthropicBackend, OpenAIBackend, MockBackend])
def test_backends_implement_the_interface(backend_class):
    assert issubclass(backend_class, BaseLLMBackend)


def test_count_tokens_default_uses_heuristic():
    # The concrete default on the ABC: ~4 characters per token.
    backend = MockBackend()
    assert backend.count_tokens("a" * 40) == 10


# ---- Real backends: missing key is rejected -----------------------------------------------


def test_anthropic_requires_api_key():
    with pytest.raises(LLMBackendError):
        AnthropicBackend(api_key=None, model="m", max_tokens=10)


def test_openai_requires_api_key():
    with pytest.raises(LLMBackendError):
        OpenAIBackend(api_key="", model="m", max_tokens=10)


# ---- MockBackend: deterministic, offline --------------------------------------------------


def test_mock_returns_prose_for_unstructured_call():
    backend = MockBackend()
    out = backend.complete("anything", system=SYSTEM_PROMPT)
    assert isinstance(out, str)
    assert "Mock summary" in out


def test_mock_returns_valid_report_json_for_structured_call():
    backend = MockBackend()
    out = backend.complete("anything", system=STRUCTURED_SYSTEM_PROMPT)
    # The JSON must validate against the real schema — that is the contract the structured
    # path relies on.
    body = ReportBody.model_validate(json.loads(out))
    assert body.headline
    assert body.anomalies[0].severity == "low"


def test_mock_stream_reconstructs_complete():
    backend = MockBackend()
    streamed = "".join(backend.stream("anything", system=SYSTEM_PROMPT))
    assert streamed == backend.complete("anything", system=SYSTEM_PROMPT)
    # And it really streamed in multiple pieces, not one lump.
    assert len(list(backend.stream("anything"))) > 1


def test_mock_needs_no_api_key():
    # The whole point: usable with zero config. No raise.
    MockBackend()


# ---- The factory --------------------------------------------------------------------------


def test_get_backend_resolves_configured_default():
    # Test settings point BACKEND at AnthropicBackend with a (dummy) key present.
    backend = get_backend()
    assert isinstance(backend, AnthropicBackend)


def test_get_backend_override_wins_over_setting():
    # Setting says Anthropic; the override should take precedence for this run.
    backend = get_backend("llm_audit.backends.mock.MockBackend")
    assert isinstance(backend, MockBackend)


@override_settings(LLM_AUDIT={"BACKEND": "llm_audit.backends.mock.MockBackend"})
def test_get_backend_reads_backend_from_settings():
    backend = get_backend()
    assert isinstance(backend, MockBackend)


def test_get_backend_bad_path_raises_improperly_configured():
    with pytest.raises(ImproperlyConfigured):
        get_backend("llm_audit.backends.does_not_exist.NoBackend")
