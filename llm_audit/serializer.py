"""Serialize Django querysets to LLM-friendly JSON.

Implemented in M2. A queryset's ``.values(*fields)`` output is dumped to JSON with
``default=str`` so Decimal/datetime/UUID fields survive serialization.
"""


def serialize_records(*args, **kwargs):
    """Placeholder. Implemented in milestone M2."""
    raise NotImplementedError
