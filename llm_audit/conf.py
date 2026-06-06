"""Settings accessor for django-llm-audit.

All plugin code reads configuration through the ``audit_settings`` object rather than
touching ``settings.LLM_AUDIT`` directly. This gives one place for defaults, validation,
and discovery of every supported setting — the same pattern Django REST Framework and
django-allauth use.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

#: Default values applied when a key is absent from ``settings.LLM_AUDIT``.
DEFAULTS = {
    # The backend to use. May be a short alias ("anthropic", "openai", "ollama", "mock" — see
    # ``backends.BACKEND_ALIASES``) or a full dotted path; both resolve at runtime via
    # import_string in ``llm_audit.backends.get_backend`` — the same string-to-class
    # indirection Django uses for EMAIL_BACKEND / CACHES / STORAGES. Override per-run with
    # ``--backend``.
    "BACKEND": "anthropic",
    # No key by default, so the plugin imports and the factory runs with zero config (the
    # MockBackend needs none). Each backend decides whether a key is required: AnthropicBackend
    # raises a clear error when it is missing; MockBackend never looks at it.
    "API_KEY": None,
    "MODEL": "claude-haiku-4-5-20251001",
    "MAX_TOKENS": 1024,
    "CHUNK_TOKEN_THRESHOLD": 3000,
    "DEFAULT_RECORD_LIMIT": 50,
}


class LLMAuditSettings:
    """Lazy accessor over ``settings.LLM_AUDIT`` with sensible defaults."""

    def __getattr__(self, name: str):
        user_settings = getattr(settings, "LLM_AUDIT", {})
        if name in user_settings:
            return user_settings[name]
        if name in DEFAULTS:
            return DEFAULTS[name]
        raise AttributeError(f"Invalid LLM_AUDIT setting: '{name}'")


#: Singleton accessor imported throughout the plugin.
audit_settings = LLMAuditSettings()


def resolve_backend_config(name: str | None = None) -> dict:
    """Resolve the configuration for a single backend into a flat dict.

    Two settings shapes are supported, and this function hides the difference from callers:

    **Named mode** — when ``LLM_AUDIT`` contains a ``BACKENDS`` dict, each entry is a
    self-contained bundle (its own ``BACKEND`` class, ``API_KEY``, ``MODEL``), the Django
    ``DATABASES`` pattern. ``LLM_AUDIT['DEFAULT']`` names the bundle used when ``name`` is not
    given. This is what makes ``--backend openai`` a real one-run switch: it selects the whole
    bundle — class *and* key *and* model — not just the class. ``BACKEND`` is required in each
    bundle. ``MAX_TOKENS`` may be set per bundle, falling back to a top-level ``MAX_TOKENS``,
    then the default.

    **Flat mode** — when there is no ``BACKENDS`` key, the whole ``LLM_AUDIT`` dict is treated
    as one implicit backend config (the original, single-provider shape). Here ``name`` is a
    backend class alias or dotted path that overrides ``BACKEND`` — the legacy behaviour, kept
    for backward compatibility.

    Args:
        name: In named mode, the bundle name to select (the ``--backend`` flag). In flat mode,
            a backend alias/dotted path overriding ``BACKEND``. ``None`` uses the configured
            default.

    Returns:
        A dict with keys ``BACKEND``, ``API_KEY``, ``MODEL``, ``MAX_TOKENS``.

    Raises:
        ImproperlyConfigured: If a named ``BACKENDS`` map has no usable default, the requested
            name is not configured, or a selected bundle omits the required ``BACKEND`` key.
    """
    user_settings = getattr(settings, "LLM_AUDIT", {})
    backends = user_settings.get("BACKENDS")

    if backends:
        chosen = name or user_settings.get("DEFAULT")
        if not chosen:
            raise ImproperlyConfigured(
                "LLM_AUDIT defines 'BACKENDS' but no 'DEFAULT'. Set LLM_AUDIT['DEFAULT'] to a "
                "configured backend name, or pass --backend <name>. "
                f"Configured backends: {', '.join(backends)}."
            )
        if chosen not in backends:
            raise ImproperlyConfigured(
                f"Unknown LLM_AUDIT backend '{chosen}'. "
                f"Configured backends: {', '.join(backends)}."
            )
        cfg = backends[chosen]
        if not cfg.get("BACKEND"):
            raise ImproperlyConfigured(
                f"LLM_AUDIT backend config '{chosen}' is missing the required 'BACKEND' key."
            )
        return {
            "BACKEND": cfg["BACKEND"],
            "API_KEY": cfg.get("API_KEY"),
            "MODEL": cfg.get("MODEL", DEFAULTS["MODEL"]),
            # Per-bundle MAX_TOKENS wins, then a top-level shared value, then the default.
            "MAX_TOKENS": cfg.get(
                "MAX_TOKENS", user_settings.get("MAX_TOKENS", DEFAULTS["MAX_TOKENS"])
            ),
        }

    # Flat / legacy mode: the whole LLM_AUDIT dict is a single implicit backend config, and
    # ``name`` (the --backend override) replaces only the backend class.
    return {
        "BACKEND": name or user_settings.get("BACKEND", DEFAULTS["BACKEND"]),
        "API_KEY": user_settings.get("API_KEY", DEFAULTS["API_KEY"]),
        "MODEL": user_settings.get("MODEL", DEFAULTS["MODEL"]),
        "MAX_TOKENS": user_settings.get("MAX_TOKENS", DEFAULTS["MAX_TOKENS"]),
    }
