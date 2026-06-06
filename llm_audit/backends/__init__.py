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
from llm_audit.conf import audit_settings

__all__ = ["BaseLLMBackend", "get_backend"]


def get_backend(override: str | None = None) -> BaseLLMBackend:
    """Resolve and instantiate the configured LLM backend.

    Selection precedence: an explicit ``override`` (the command's ``--backend`` flag) wins;
    otherwise ``LLM_AUDIT['BACKEND']``; otherwise the default in ``conf.DEFAULTS``. The chosen
    dotted path is resolved to a class with Django's ``import_string`` — the same machinery
    behind ``EMAIL_BACKEND`` and ``CACHES`` — so this function depends on no concrete provider.

    Every backend is constructed with the same standard keyword arguments
    (``api_key``/``model``/``max_tokens``). Backends that don't need them (``MockBackend``)
    simply ignore them. Whether an API key is *required* is each backend's own call, made in
    its ``__init__`` — not the factory's.

    Args:
        override: A dotted path to a backend class, overriding the configured one for this run.

    Returns:
        A ready-to-use backend instance implementing :class:`BaseLLMBackend`.

    Raises:
        ImproperlyConfigured: If the dotted path cannot be imported.
    """
    path = override or audit_settings.BACKEND

    try:
        backend_class = import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(f"Could not import LLM_AUDIT backend '{path}': {exc}") from exc

    return backend_class(
        api_key=audit_settings.API_KEY,
        model=audit_settings.MODEL,
        max_tokens=audit_settings.MAX_TOKENS,
    )
