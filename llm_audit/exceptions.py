"""Custom exceptions for django-llm-audit."""


class LLMAuditError(Exception):
    """Base class for all django-llm-audit errors."""


class LLMBackendError(LLMAuditError):
    """Raised when an LLM backend fails to produce a response."""


class ChunkingError(LLMAuditError):
    """Raised when records cannot be chunked within the configured token threshold."""
