"""Django AppConfig for the llm_audit plugin."""

from django.apps import AppConfig


class LLMAuditConfig(AppConfig):
    """App configuration for django-llm-audit."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "llm_audit"
    verbose_name = "LLM Audit"
