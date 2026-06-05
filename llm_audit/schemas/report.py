"""Pydantic schemas for the structured summary report (M4).

These types are the contract between the LLM and the rest of the plugin. Instead of
free-text prose (M1–M3), the structured path instructs the model to return JSON, which we
validate against :class:`ReportBody`. Validation gives us type safety, clear errors, and a
single place that defines what a "report" is.

Two-layer design — the key M4 decision:

* :class:`ReportBody` is what the **LLM** produces. It holds only the *analytical* fields,
  the things that genuinely require reading the data: the headline, patterns, anomalies,
  and assessment.
* :class:`SummaryReport` is the **full artifact**. It wraps a ``ReportBody`` with metadata
  we already hold in Python — the model name, the record count, and the generation
  timestamp. We never ask the LLM for facts we already know: it cannot miscount records or
  misname the table if it is never asked to produce those values.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Anomaly(BaseModel):
    """A single unusual finding in the data.

    ``severity`` is a strict enum on purpose. It is the field an LLM is most likely to get
    subtly wrong (e.g. returning ``"critical"`` or ``"High"``), which makes it the natural
    trigger for the retry logic in the summarizer — and a good lens for understanding how
    often models drift from an instructed format.
    """

    field: str = Field(description="The record field the anomaly relates to.")
    description: str = Field(description="What is unusual, in one or two sentences.")
    severity: Literal["low", "medium", "high"] = Field(
        description="How serious the anomaly looks: one of 'low', 'medium', 'high'."
    )


class ReportBody(BaseModel):
    """The analytical core of a report — exactly what the LLM is asked to return as JSON.

    Deliberately excludes ``model_name``, ``record_count``, and ``generated_at``: those are
    facts we already hold and inject ourselves (see :class:`SummaryReport`).
    """

    headline: str = Field(description="A one-sentence key insight for the whole dataset.")
    patterns: list[str] = Field(description="3-5 key patterns or trends, each a short bullet.")
    anomalies: list[Anomaly] = Field(
        description="Unusual values or findings; an empty list if none stand out."
    )
    assessment: str = Field(description="A 2-3 sentence overall assessment.")


class SummaryReport(BaseModel):
    """A complete audit report: the LLM's analysis plus metadata we inject in Python.

    Built via :meth:`from_body` rather than constructed by the model, so the deterministic
    fields are always correct regardless of what the LLM returns.
    """

    model_name: str
    record_count: int
    generated_at: datetime
    headline: str
    patterns: list[str]
    anomalies: list[Anomaly]
    assessment: str

    @classmethod
    def from_body(
        cls,
        body: ReportBody,
        *,
        model_name: str,
        record_count: int,
        generated_at: datetime,
    ) -> "SummaryReport":
        """Compose a full report from a validated ``ReportBody`` and known metadata.

        Args:
            body: The LLM's validated analytical output.
            model_name: The audited Django model's class name.
            record_count: How many records were audited.
            generated_at: When the report was produced.

        Returns:
            A fully-populated :class:`SummaryReport`.
        """
        return cls(
            model_name=model_name,
            record_count=record_count,
            generated_at=generated_at,
            headline=body.headline,
            patterns=body.patterns,
            anomalies=body.anomalies,
            assessment=body.assessment,
        )
