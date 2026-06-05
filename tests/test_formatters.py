"""Tests for the M4 output formatters.

Pure functions over a known ``SummaryReport`` — no LLM, no DB. We check that each format
carries the data faithfully and that the empty-anomalies branch reads sensibly.
"""

import json
from datetime import datetime, timezone

import pytest

from llm_audit.formatters import render, to_json, to_markdown, to_text
from llm_audit.schemas.report import Anomaly, SummaryReport


def _report(anomalies=None):
    return SummaryReport(
        model_name="Order",
        record_count=300,
        generated_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
        headline="Refunds concentrate in Electronics.",
        patterns=["Most orders delivered.", "Totals cluster 20-80."],
        anomalies=(
            anomalies
            if anomalies is not None
            else [Anomaly(field="status", description="Refund spike.", severity="high")]
        ),
        assessment="Healthy overall with one outlier category.",
    )


def test_to_json_round_trips_to_the_same_data():
    report = _report()

    payload = json.loads(to_json(report))

    assert payload["model_name"] == "Order"
    assert payload["record_count"] == 300
    assert payload["anomalies"][0]["severity"] == "high"


def test_to_text_includes_headline_patterns_and_anomaly():
    text = to_text(_report())

    assert "Order (300 records)" in text
    assert "Refunds concentrate in Electronics." in text
    assert "Most orders delivered." in text
    assert "[HIGH] status" in text


def test_to_text_handles_no_anomalies():
    text = to_text(_report(anomalies=[]))

    assert "None detected." in text


def test_to_markdown_has_headings_and_severity_code():
    md = to_markdown(_report())

    assert md.startswith("# Audit report — Order")
    assert "## Patterns" in md
    assert "**status** (`high`)" in md


def test_to_markdown_handles_no_anomalies():
    md = to_markdown(_report(anomalies=[]))

    assert "_None detected._" in md


def test_render_dispatches_by_format_name():
    report = _report()

    assert render(report, "json") == to_json(report)
    assert render(report, "markdown") == to_markdown(report)
    assert render(report, "text") == to_text(report)


def test_render_rejects_unknown_format():
    with pytest.raises(ValueError, match="Unknown format"):
        render(_report(), "xml")
