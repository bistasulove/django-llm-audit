"""Pluggable LLM backends for django-llm-audit.

This package holds the backend abstraction (:class:`~llm_audit.backends.base.BaseLLMBackend`),
the concrete implementations, and :func:`get_backend` — the factory that turns the configured
dotted-path string into a live backend instance.

``get_backend`` is the seam introduced in M5. Before it, the management command named
``AnthropicBackend`` directly; now it asks for *the configured backend* and never mentions a
provider. That one indirection is the Dependency Inversion Principle made concrete.
"""

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from llm_audit.backends.base import BaseLLMBackend
from llm_audit.conf import resolve_backend_config

__all__ = ["BACKEND_ALIASES", "BaseLLMBackend", "get_backend"]

#: Short, friendly names for the built-in backends. Users may write ``"anthropic"`` instead of
#: the full ``"llm_audit.backends.anthropic.AnthropicBackend"`` dotted path in their settings or
#: ``--backend`` flag — lower wiring, fewer typos. Any value that is *not* a known alias is
#: treated as a dotted path and resolved as-is, so custom/third-party backends still work.
BACKEND_ALIASES = {
    "anthropic": "llm_audit.backends.anthropic.AnthropicBackend",
    "openai": "llm_audit.backends.openai.OpenAIBackend",
    "ollama": "llm_audit.backends.ollama.OllamaBackend",
    "mock": "llm_audit.backends.mock.MockBackend",
}


def get_backend(name: str | None = None) -> BaseLLMBackend:
    """Resolve and instantiate the configured LLM backend.

    The configuration (which class, which key, which model, which token budget) is resolved by
    :func:`llm_audit.conf.resolve_backend_config`, which transparently handles both settings
    shapes:

    - **Named mode** (``LLM_AUDIT['BACKENDS']`` present): ``name`` selects a whole bundle —
      class *and* key *and* model together — so ``--backend openai`` is a real one-run provider
      switch. ``None`` uses ``LLM_AUDIT['DEFAULT']``.
    - **Flat mode** (single-provider ``LLM_AUDIT``): ``name`` overrides only the backend class
      (the legacy behaviour).

    The resolved ``BACKEND`` value may be a short alias (``"anthropic"``, ``"openai"``,
    ``"ollama"``, ``"mock"`` — see :data:`BACKEND_ALIASES`) or a full dotted path; either way
    it is turned into a class with Django's ``import_string`` — the same machinery behind
    ``EMAIL_BACKEND`` and ``CACHES`` — so this function depends on no concrete provider.

    Every backend is constructed with the same standard keyword arguments
    (``api_key``/``model``/``max_tokens``). Backends that don't need them (``MockBackend``)
    simply ignore them. Whether an API key is *required* is each backend's own call, made in
    its ``__init__`` — not the factory's.

    Args:
        name: The backend to use — a bundle name (named mode) or an alias/dotted path (flat
            mode), overriding the configured default for this run. ``None`` uses the default.

    Returns:
        A ready-to-use backend instance implementing :class:`BaseLLMBackend`.

    Raises:
        ImproperlyConfigured: If the configuration is invalid (see
            :func:`~llm_audit.conf.resolve_backend_config`) or the resolved class cannot be
            imported.
    """
    config = resolve_backend_config(name)
    # Expand a short alias to its dotted path; leave any other value untouched so custom
    # backends (and full dotted paths) resolve unchanged.
    path = BACKEND_ALIASES.get(config["BACKEND"], config["BACKEND"])

    try:
        backend_class = import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(f"Could not import LLM_AUDIT backend '{path}': {exc}") from exc

    return backend_class(
        api_key=config["API_KEY"],
        model=config["MODEL"],
        max_tokens=config["MAX_TOKENS"],
    )
