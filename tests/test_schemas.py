"""Tests for the M4 Pydantic report schemas.

We test validation success and failure (CLAUDE.md §11) — the contract the structured path
relies on. The point of M4 is that we never trust raw LLM output: these are the rules that
output must satisfy, and ``from_body`` is where the metadata we inject (never the LLM) lands.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from llm_audit.schemas.report import Anomaly, ReportBody, SummaryReport

VALID_BODY = {
    "headline": "Orders cluster in one category.",
    "patterns": ["Most are delivered.", "Totals sit between 20 and 80."],
    "anomalies": [{"field": "status", "description": "Refund spike.", "severity": "high"}],
    "assessment": "Healthy overall with one outlier category.",
}


def test_report_body_validates_well_formed_payload():
    body = ReportBody.model_validate(VALID_BODY)

    assert body.headline.startswith("Orders")
    assert len(body.anomalies) == 1
    assert body.anomalies[0].severity == "high"


def test_report_body_allows_empty_anomalies():
    payload = {**VALID_BODY, "anomalies": []}

    body = ReportBody.model_validate(payload)

    assert body.anomalies == []


def test_report_body_rejects_out_of_enum_severity():
    # "critical" is not in the Literal — the field most likely to trip the retry loop.
    payload = {
        **VALID_BODY,
        "anomalies": [{"field": "status", "description": "x", "severity": "critical"}],
    }

    with pytest.raises(ValidationError):
        ReportBody.model_validate(payload)


def test_report_body_rejects_missing_required_field():
    payload = {k: v for k, v in VALID_BODY.items() if k != "assessment"}

    with pytest.raises(ValidationError):
        ReportBody.model_validate(payload)


def test_from_body_injects_metadata_not_taken_from_llm():
    body = ReportBody.model_validate(VALID_BODY)
    generated = datetime(2026, 6, 4, tzinfo=timezone.utc)

    report = SummaryReport.from_body(
        body, model_name="Order", record_count=42, generated_at=generated
    )

    # The deterministic facts come from us, not the model output.
    assert report.model_name == "Order"
    assert report.record_count == 42
    assert report.generated_at == generated
    # The analytical fields are carried straight through.
    assert report.headline == body.headline
    assert report.anomalies == body.anomalies


def test_anomaly_requires_all_fields():
    with pytest.raises(ValidationError):
        Anomaly.model_validate({"field": "status", "severity": "low"})
