"""Tests for llm_audit.serializer (M2)."""

import json
from datetime import datetime
from decimal import Decimal

from llm_audit.serializer import serialize_records


def test_serializes_to_valid_json_roundtrip():
    records = [{"id": 1, "status": "paid"}, {"id": 2, "status": "refunded"}]
    result = serialize_records(records)
    assert json.loads(result) == records


def test_default_str_handles_decimal_and_datetime():
    # Decimal and datetime are not natively JSON-serializable; default=str is what keeps
    # json.dumps from raising TypeError on Django's most common field types.
    records = [{"total": Decimal("19.99"), "created_at": datetime(2026, 6, 4, 12, 0, 0)}]
    result = serialize_records(records)
    parsed = json.loads(result)
    assert parsed[0]["total"] == "19.99"
    assert parsed[0]["created_at"] == "2026-06-04 12:00:00"


def test_indent_none_is_more_compact_than_indented():
    records = [{"a": 1, "b": 2}]
    assert len(serialize_records(records, indent=None)) < len(serialize_records(records))


def test_empty_list_serializes_to_empty_json_array():
    assert serialize_records([]) == "[]"
