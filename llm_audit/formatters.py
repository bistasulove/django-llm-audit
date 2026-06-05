"""Render a :class:`~llm_audit.schemas.report.SummaryReport` to a chosen output format.

The structured pipeline (M4) produces one canonical object — a ``SummaryReport`` — and
these pure functions turn it into the ``text``, ``json``, or ``markdown`` the user asked
for. Keeping rendering here (rather than in the schema or the command) makes each format a
small, independently testable unit, and keeps presentation out of the library's core.

``json`` is the report's own serialization; ``text`` and ``markdown`` are human-facing
shapes of the same data.
"""

from llm_audit.schemas.report import Anomaly, SummaryReport

#: Maps the chosen ``--format`` to its renderer. The command looks the format up here.
FORMATTERS = {}


def _register(name: str):
    """Register a renderer under a ``--format`` name."""

    def decorator(func):
        FORMATTERS[name] = func
        return func

    return decorator


def render(report: SummaryReport, fmt: str) -> str:
    """Render ``report`` in format ``fmt`` (``"text"``, ``"json"``, or ``"markdown"``)."""
    try:
        return FORMATTERS[fmt](report)
    except KeyError:
        raise ValueError(
            f"Unknown format '{fmt}'. Choose one of: {', '.join(sorted(FORMATTERS))}."
        ) from None


@_register("json")
def to_json(report: SummaryReport) -> str:
    """Serialize the report as indented JSON (the report's own canonical form)."""
    return report.model_dump_json(indent=2)


@_register("text")
def to_text(report: SummaryReport) -> str:
    """Render the report as plain numbered text for terminal reading."""
    lines = [
        f"Audit report for {report.model_name} ({report.record_count} records)",
        f"Generated {report.generated_at.isoformat()}",
        "",
        f"Headline: {report.headline}",
        "",
        "Patterns:",
    ]
    lines += [f"  - {pattern}" for pattern in report.patterns]
    lines += ["", "Anomalies:"]
    if report.anomalies:
        lines += [f"  - {_anomaly_text(a)}" for a in report.anomalies]
    else:
        lines.append("  - None detected.")
    lines += ["", "Assessment:", report.assessment]
    return "\n".join(lines)


@_register("markdown")
def to_markdown(report: SummaryReport) -> str:
    """Render the report as Markdown, ready to paste into a doc or PR."""
    lines = [
        f"# Audit report — {report.model_name}",
        "",
        f"- **Records analyzed:** {report.record_count}",
        f"- **Generated:** {report.generated_at.isoformat()}",
        "",
        "## Headline",
        report.headline,
        "",
        "## Patterns",
    ]
    lines += [f"- {pattern}" for pattern in report.patterns]
    lines += ["", "## Anomalies"]
    if report.anomalies:
        lines += [f"- **{a.field}** (`{a.severity}`): {a.description}" for a in report.anomalies]
    else:
        lines.append("_None detected._")
    lines += ["", "## Assessment", report.assessment]
    return "\n".join(lines)


def _anomaly_text(anomaly: Anomaly) -> str:
    """One-line plain-text rendering of an anomaly, severity first for scannability."""
    return f"[{anomaly.severity.upper()}] {anomaly.field}: {anomaly.description}"
