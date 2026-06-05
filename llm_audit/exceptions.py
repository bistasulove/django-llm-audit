"""Custom exceptions for django-llm-audit."""


class LLMAuditError(Exception):
    """Base class for all django-llm-audit errors."""


class LLMBackendError(LLMAuditError):
    """Raised when an LLM backend fails to produce a response."""


class ChunkingError(LLMAuditError):
    """Raised when records cannot be chunked within the configured token threshold."""


class StructuredOutputError(LLMAuditError):
    """Raised when the LLM cannot produce valid, schema-conforming JSON after retries.

    Distinct from :class:`LLMBackendError`: the backend succeeded in returning text, but
    that text could not be parsed as JSON or did not match the report schema, even after
    the configured retries.
    """
