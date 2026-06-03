"""Settings accessor for django-llm-audit.

All plugin code reads configuration through the ``audit_settings`` object rather than
touching ``settings.LLM_AUDIT`` directly. This gives one place for defaults, validation,
and discovery of every supported setting — the same pattern Django REST Framework and
django-allauth use.
"""

from django.conf import settings

#: Default values applied when a key is absent from ``settings.LLM_AUDIT``.
DEFAULTS = {
    "MODEL": "claude-opus-4-5",
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
