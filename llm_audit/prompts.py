"""Prompt templates for django-llm-audit.

All prompt strings live here, never inline in the summarizer or management command.
Prompts are code: version-controlled, reviewed, and tested. Populated in M1+.
"""

#: Sets the model's role and rules. Sent as the ``system`` prompt so it steers the
#: whole response without competing with the data for the model's attention.
#:
#: The grounding rules here are deliberately *universal* — true for any real Django
#: project's data, not tailored to the demo. They keep the model honest about the limits
#: of what it was given (a flat extract) instead of inventing relationships or causes.
SYSTEM_PROMPT = (
    "You are a data analyst reviewing database records from a Django application. "
    "Be specific and concrete, and reference actual values. Do not speculate beyond the "
    "data you are given.\n\n"
    "You are working from a flat extract of a single table: only the listed fields are "
    "present, and related tables (foreign keys, reverse relations) are NOT included. If a "
    "conclusion would require information outside these fields — for example breaking a "
    "metric down by a related table — say so explicitly instead of guessing.\n\n"
    "Distinguish genuine business anomalies from likely data artifacts. For instance, an "
    "identical timestamp across every row usually reflects a bulk update or migration "
    "rather than a real-world event; an apparent correlation between two independent "
    "fields may be coincidence. Do not assert causation from correlation, and state your "
    "confidence when something is uncertain."
)

#: The task + data, sent as the ``user`` message. The numbered structure produces
#: predictable, scannable output — the precursor to M4's structured JSON.
AUDIT_TASK_TEMPLATE = """Analyze the following {record_count} records from the '{model_name}' table.

These are the only fields available for each record (a flat, single-table extract):
{field_list}

Provide:
1. A one-sentence headline insight
2. Key patterns and trends (3-5 bullet points)
3. Anomalies or unusual values — for each, note whether it looks like a genuine business
   signal or a possible data artifact, and how confident you are
4. A brief overall assessment (2-3 sentences)

[Data]
{records_json}
"""


def build_audit_prompt(
    model_name: str,
    record_count: int,
    records_json: str,
    field_names: list[str],
) -> tuple[str, str]:
    """Build the prompt for an audit run.

    Args:
        model_name: The Django model's class name (e.g. ``"Order"``).
        record_count: How many records are included in ``records_json``.
        records_json: The records serialized as a JSON string.
        field_names: The field names present in each record. Listed explicitly so the
            model knows exactly what it has — and, just as importantly, what it lacks.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    field_list = ", ".join(field_names)
    user_prompt = AUDIT_TASK_TEMPLATE.format(
        record_count=record_count,
        model_name=model_name,
        field_list=field_list,
        records_json=records_json,
    )
    return SYSTEM_PROMPT, user_prompt
