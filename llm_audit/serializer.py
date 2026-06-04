"""Serialize Django queryset records to LLM-friendly JSON.

Implemented in M2, extracted from M1's inline ``json.dumps`` in the management command.
The input is a list of dicts (as produced by ``QuerySet.values()``), not a queryset, so
this stays free of any Django import and is trivially unit-testable.

JSON is the format ADR-004 settles on: field names carry semantic meaning the LLM can
use, and it is the structure LLMs handle best. The one Django gotcha it papers over is
``default=str`` — ``Decimal``, ``datetime``, and ``UUID`` are not natively JSON
serializable, and without it ``json.dumps`` raises ``TypeError`` on the first one it hits.
"""

import json


def serialize_records(records: list[dict], *, indent: int = 2) -> str:
    """Serialize a list of record dicts to a JSON string.

    Args:
        records: Records as dicts, typically from ``QuerySet.values()``.
        indent: Indentation passed through to ``json.dumps``. Readable output by
            default; pass ``None`` for the most compact (fewest-token) form.

    Returns:
        The records as a JSON-formatted string.
    """
    return json.dumps(records, default=str, indent=indent)
