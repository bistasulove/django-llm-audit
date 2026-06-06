"""Tests for llm_audit.backends (M5).

We test the abstraction and the factory, plus MockBackend's deterministic behaviour. We do
*not* make real Anthropic/OpenAI calls — those SDKs are external I/O, not our code (CLAUDE.md
§11). The real backends are covered here only for the parts that are ours: that they conform
to the interface and that they reject a missing API key.
"""

import io
import json
from urllib.error import HTTPError, URLError

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from llm_audit.backends import get_backend
from llm_audit.backends.anthropic import AnthropicBackend
from llm_audit.backends.base import BaseLLMBackend
from llm_audit.backends.mock import MockBackend
from llm_audit.backends.ollama import DEFAULT_HOST, OllamaBackend
from llm_audit.backends.openai import OpenAIBackend
from llm_audit.conf import resolve_backend_config
from llm_audit.exceptions import LLMAuditError, LLMBackendError
from llm_audit.prompts import STRUCTURED_SYSTEM_PROMPT, SYSTEM_PROMPT
from llm_audit.schemas.report import ReportBody

# A reusable named-backends settings block (the Django DATABASES-style shape). Each bundle is
# self-contained; switching by name swaps class + key + model together.
_NAMED_SETTINGS = {
    "DEFAULT": "claude",
    "BACKENDS": {
        "claude": {"BACKEND": "anthropic", "API_KEY": "ak", "MODEL": "claude-x"},
        "gpt": {"BACKEND": "openai", "API_KEY": "ok", "MODEL": "gpt-x"},
        "local": {"BACKEND": "ollama", "MODEL": "llama3.1"},
    },
    "MAX_TOKENS": 999,
}

# ---- The abstraction ----------------------------------------------------------------------


def test_base_backend_is_abstract():
    with pytest.raises(TypeError):
        BaseLLMBackend()  # cannot instantiate an ABC with abstract methods


def test_backend_error_hierarchy():
    assert issubclass(LLMBackendError, LLMAuditError)


@pytest.mark.parametrize(
    "backend_class", [AnthropicBackend, OpenAIBackend, OllamaBackend, MockBackend]
)
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


@pytest.mark.parametrize(
    "alias,expected",
    [
        ("anthropic", AnthropicBackend),
        ("openai", OpenAIBackend),
        ("ollama", OllamaBackend),
        ("mock", MockBackend),
    ],
)
def test_get_backend_resolves_short_aliases(alias, expected):
    # The low-wiring win: a friendly name resolves to the right backend (test settings supply
    # the dummy API_KEY the real backends require at construction).
    assert isinstance(get_backend(alias), expected)


@override_settings(LLM_AUDIT={"BACKEND": "ollama"})
def test_get_backend_alias_works_from_settings():
    assert isinstance(get_backend(), OllamaBackend)


def test_get_backend_unknown_value_is_treated_as_dotted_path():
    # Anything that isn't a known alias must fall through to import_string unchanged, so custom
    # backends keep working. A bogus path therefore still raises ImproperlyConfigured.
    with pytest.raises(ImproperlyConfigured):
        get_backend("not_an_alias_and_not_a_real_path")


# ---- OllamaBackend: raw HTTP, no SDK, no key (urlopen mocked) ------------------------------


class _FakeResponse:
    """Stand-in for the object ``urlopen`` returns: a context manager that is readable (for
    the blocking call) and iterable line-by-line (for the NDJSON stream)."""

    def __init__(self, *, body: bytes = b"", lines: list[bytes] | None = None):
        self._body = body
        self._lines = lines or []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body

    def __iter__(self):
        return iter(self._lines)


def test_ollama_needs_no_api_key():
    # Like MockBackend: a local server has nothing to authenticate, so no raise.
    OllamaBackend(api_key=None, model="llama3.1", max_tokens=10)


def test_ollama_host_defaults_then_honors_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert OllamaBackend().host == DEFAULT_HOST
    # A bare host:port gets a scheme prepended; a trailing slash is trimmed.
    monkeypatch.setenv("OLLAMA_HOST", "192.168.1.5:11434/")
    assert OllamaBackend().host == "http://192.168.1.5:11434"


def test_ollama_complete_builds_chat_request_and_returns_content(monkeypatch):
    captured = {}
    payload = json.dumps(
        {"message": {"role": "assistant", "content": "Hello from llama."}, "done": True}
    ).encode()

    def fake_urlopen(request, *args, **kwargs):
        captured["request"] = request
        return _FakeResponse(body=payload)

    monkeypatch.setattr("llm_audit.backends.ollama.urlopen", fake_urlopen)

    backend = OllamaBackend(model="llama3.1", max_tokens=256)
    assert backend.complete("the data", system="be terse") == "Hello from llama."

    request = captured["request"]
    assert request.full_url == f"{DEFAULT_HOST}/api/chat"
    sent = json.loads(request.data)
    assert sent["model"] == "llama3.1"
    assert sent["stream"] is False
    assert sent["options"]["num_predict"] == 256
    # System prompt rides as the first message (Ollama, like OpenAI, has no top-level system).
    assert sent["messages"][0] == {"role": "system", "content": "be terse"}
    assert sent["messages"][1] == {"role": "user", "content": "the data"}


def test_ollama_stream_yields_ndjson_pieces(monkeypatch):
    lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}).encode(),
        json.dumps({"message": {"content": " world"}, "done": False}).encode(),
        json.dumps({"message": {"content": ""}, "done": True}).encode(),
    ]
    monkeypatch.setattr(
        "llm_audit.backends.ollama.urlopen", lambda request, *a, **k: _FakeResponse(lines=lines)
    )

    pieces = list(OllamaBackend(model="llama3.1").stream("hi"))
    assert pieces == ["Hello", " world"]
    assert "".join(pieces) == "Hello world"


def test_ollama_unreachable_raises_actionable_error(monkeypatch):
    def fake_urlopen(request, *args, **kwargs):
        raise URLError("Connection refused")

    monkeypatch.setattr("llm_audit.backends.ollama.urlopen", fake_urlopen)

    backend = OllamaBackend(model="llama3.1")
    with pytest.raises(LLMBackendError, match="Is it running"):
        backend.complete("hi")


def test_ollama_stream_unreachable_raises_on_iteration(monkeypatch):
    def fake_urlopen(request, *args, **kwargs):
        raise URLError("Connection refused")

    monkeypatch.setattr("llm_audit.backends.ollama.urlopen", fake_urlopen)

    # stream() is a generator: the error must surface when consumed, not when called.
    gen = OllamaBackend(model="llama3.1").stream("hi")
    with pytest.raises(LLMBackendError, match="Is it running"):
        list(gen)


# ---- Named backend configs (Django DATABASES-style) ---------------------------------------


@override_settings(LLM_AUDIT=_NAMED_SETTINGS)
def test_resolve_named_config_uses_default_when_unspecified():
    cfg = resolve_backend_config()  # no name -> LLM_AUDIT["DEFAULT"] == "claude"
    assert cfg == {"BACKEND": "anthropic", "API_KEY": "ak", "MODEL": "claude-x", "MAX_TOKENS": 999}


@override_settings(LLM_AUDIT=_NAMED_SETTINGS)
def test_resolve_named_config_selects_bundle_by_name():
    cfg = resolve_backend_config("gpt")
    assert cfg["BACKEND"] == "openai"
    assert cfg["API_KEY"] == "ok"
    assert cfg["MODEL"] == "gpt-x"


@override_settings(LLM_AUDIT=_NAMED_SETTINGS)
def test_resolve_named_config_max_tokens_falls_back_to_top_level():
    # The "local" bundle sets no MAX_TOKENS, so it inherits the top-level 999.
    assert resolve_backend_config("local")["MAX_TOKENS"] == 999


@override_settings(
    LLM_AUDIT={
        "DEFAULT": "local",
        "BACKENDS": {"local": {"BACKEND": "ollama", "MODEL": "m", "MAX_TOKENS": 42}},
    }
)
def test_resolve_named_config_per_bundle_max_tokens_wins():
    assert resolve_backend_config()["MAX_TOKENS"] == 42


@override_settings(LLM_AUDIT=_NAMED_SETTINGS)
def test_resolve_named_config_unknown_name_raises():
    with pytest.raises(ImproperlyConfigured, match="Unknown LLM_AUDIT backend 'nope'"):
        resolve_backend_config("nope")


@override_settings(LLM_AUDIT={"BACKENDS": {"claude": {"BACKEND": "anthropic"}}})
def test_resolve_named_config_missing_default_raises():
    # BACKENDS present but no DEFAULT and no explicit name -> cannot choose.
    with pytest.raises(ImproperlyConfigured, match="no 'DEFAULT'"):
        resolve_backend_config()


@override_settings(LLM_AUDIT={"DEFAULT": "x", "BACKENDS": {"x": {"MODEL": "m"}}})
def test_resolve_named_config_bundle_without_backend_raises():
    with pytest.raises(ImproperlyConfigured, match="missing the required 'BACKEND'"):
        resolve_backend_config()


@override_settings(LLM_AUDIT=_NAMED_SETTINGS)
def test_get_backend_named_default_builds_wired_instance():
    backend = get_backend()  # default "claude" bundle
    assert isinstance(backend, AnthropicBackend)
    # The bundle's key and model are actually wired into the instance.
    assert backend.model == "claude-x"
    assert backend.api_key == "ak"
    assert backend.max_tokens == 999


@override_settings(LLM_AUDIT=_NAMED_SETTINGS)
def test_get_backend_named_selector_switches_whole_bundle():
    # The headline fix: --backend selects class + key + model together.
    backend = get_backend("gpt")
    assert isinstance(backend, OpenAIBackend)
    assert backend.model == "gpt-x"
    assert backend.api_key == "ok"


@override_settings(LLM_AUDIT=_NAMED_SETTINGS)
def test_get_backend_named_local_bundle_needs_no_key():
    backend = get_backend("local")
    assert isinstance(backend, OllamaBackend)
    assert backend.model == "llama3.1"


def test_ollama_http_error_surfaces_server_message(monkeypatch):
    body = io.BytesIO(json.dumps({"error": "model 'x' not found, try pulling it first"}).encode())

    def fake_urlopen(request, *args, **kwargs):
        raise HTTPError(
            url="http://localhost:11434/api/chat",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=body,
        )

    monkeypatch.setattr("llm_audit.backends.ollama.urlopen", fake_urlopen)

    backend = OllamaBackend(model="x")
    with pytest.raises(LLMBackendError, match="not found"):
        backend.complete("hi")
