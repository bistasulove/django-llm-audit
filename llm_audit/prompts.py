"""Prompt templates for django-llm-audit.

All prompt strings live here, never inline in the summarizer or management command.
Prompts are code: version-controlled, reviewed, and tested. Populated in M1+.

M4 adds the *structured* variants. Where the prose prompts (M1–M3) ask for numbered
free-text sections, the structured prompts instruct the model to return a single JSON
object matching :class:`~llm_audit.schemas.report.ReportBody`, which the summarizer then
validates with Pydantic.
"""

from llm_audit.schemas.report import Anomaly, ReportBody

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


#: The reduce-step system prompt. Used in M2's map-reduce when records span more than
#: one chunk: each chunk is summarized independently (the "map" step, reusing
#: SYSTEM_PROMPT above), then those partial summaries are combined here (the "reduce"
#: step). The model now reasons over *summaries of the same table*, not raw rows, so the
#: grounding is different: warn it that detail has already been lossy-compressed, that
#: partials may overlap or disagree, and that it must not fabricate specifics it can no
#: longer see in the underlying data.
META_SYSTEM_PROMPT = (
    "You are a data analyst combining several partial analyses into one final report. "
    "Each partial analysis below covers a different, non-overlapping subset of rows from "
    "the same database table; together they describe the whole dataset.\n\n"
    "Synthesize them into a single coherent summary. Reconcile and aggregate findings "
    "across the partials: merge patterns that recur, and treat a pattern seen in several "
    "partials as stronger than one seen in only one. Where partials disagree or a count "
    "cannot be summed exactly from what you are given, say so rather than inventing a "
    "precise figure.\n\n"
    "You are working from summaries, not the original rows — detail has already been "
    "compressed, so do not fabricate specific values that are not present in the partials. "
    "Do not assert causation from correlation, and state your confidence when uncertain."
)

#: The reduce-step task + data. Mirrors AUDIT_TASK_TEMPLATE's numbered structure so the
#: final multi-chunk output is shaped identically to a single-chunk run.
META_TASK_TEMPLATE = """The following {chunk_count} partial analyses together cover all \
{record_count} records from the '{model_name}' table, split across chunks for processing.

Combine them into one final report with the same structure:
1. A one-sentence headline insight for the whole dataset
2. Key patterns and trends (3-5 bullet points), aggregated across the partials
3. Anomalies or unusual values — for each, note whether it looks like a genuine business
   signal or a possible data artifact, and how confident you are
4. A brief overall assessment (2-3 sentences)

[Partial analyses]
{summaries_block}
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


def build_meta_prompt(
    model_name: str,
    record_count: int,
    chunk_summaries: list[str],
) -> tuple[str, str]:
    """Build the reduce-step prompt that combines per-chunk summaries into one.

    Args:
        model_name: The Django model's class name (e.g. ``"Order"``).
        record_count: Total records across all chunks (the whole dataset).
        chunk_summaries: The per-chunk summaries from the map step, in order.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    # Label each partial so the model can refer to them and weigh recurrence. The blank
    # lines keep the boundaries legible to the model.
    summaries_block = "\n\n".join(
        f"--- Partial analysis {i} of {len(chunk_summaries)} ---\n{summary}"
        for i, summary in enumerate(chunk_summaries, start=1)
    )
    user_prompt = META_TASK_TEMPLATE.format(
        chunk_count=len(chunk_summaries),
        record_count=record_count,
        model_name=model_name,
        summaries_block=summaries_block,
    )
    return META_SYSTEM_PROMPT, user_prompt


# --------------------------------------------------------------------------------------
# Structured (JSON) prompts — M4
# --------------------------------------------------------------------------------------

#: A concrete example of the expected output, built from a *real* validated ``ReportBody``
#: instance. Models follow a worked example more reliably than a raw JSON Schema, and
#: because this is an actual instance, any incompatible change to the schema breaks this
#: line loudly at import — the prompt can never silently drift from the type it must match.
_EXAMPLE_BODY = ReportBody(
    headline="Refunds are concentrated in a single product category.",
    patterns=[
        "Most orders are in the 'delivered' status.",
        "Order totals cluster between 20 and 80.",
        "Order volume rises sharply in one month versus the rest.",
    ],
    anomalies=[
        Anomaly(
            field="status",
            description="The 'refunded' rate is several times higher than any other month.",
            severity="high",
        )
    ],
    assessment=(
        "The dataset looks healthy overall, with one category driving most refunds. "
        "That category is worth a closer, relation-aware look outside this flat extract."
    ),
)
_EXAMPLE_JSON = _EXAMPLE_BODY.model_dump_json(indent=2)

#: Appended to the grounding system prompts to demand JSON-only output. Shared by the
#: single-chunk and reduce structured prompts so the contract is stated once.
JSON_OUTPUT_RULE = (
    "Return your analysis as a single JSON object and nothing else. Do not wrap it in "
    "markdown code fences, and do not write any text before or after the JSON. The object "
    "must match this structure exactly — this example shows the shape and types, not real "
    f"values:\n\n{_EXAMPLE_JSON}\n\n"
    'Every field is required. "severity" must be exactly one of "low", "medium", or '
    '"high" (lowercase). "anomalies" may be an empty list if nothing genuinely stands out.'
)

#: System prompt for a single-chunk / terminal structured run. Reuses the universal
#: grounding from :data:`SYSTEM_PROMPT` and adds the JSON-output contract.
STRUCTURED_SYSTEM_PROMPT = f"{SYSTEM_PROMPT}\n\n{JSON_OUTPUT_RULE}"

#: System prompt for the structured reduce step. Reuses the reduce-grounding from
#: :data:`META_SYSTEM_PROMPT` (it reasons over summaries, not raw rows) plus the contract.
STRUCTURED_META_SYSTEM_PROMPT = f"{META_SYSTEM_PROMPT}\n\n{JSON_OUTPUT_RULE}"

#: The structured single-chunk task. The output *shape* is dictated by the system prompt,
#: so the user message only has to deliver the data and what to look at.
STRUCTURED_AUDIT_TASK_TEMPLATE = (
    "Analyze the following {record_count} records from the '{model_name}' table.\n\n"
    "These are the only fields available for each record (a flat, single-table extract):\n"
    "{field_list}\n\n"
    "[Data]\n"
    "{records_json}\n"
)

#: The structured reduce task: combine the per-chunk prose summaries into one JSON object.
STRUCTURED_META_TASK_TEMPLATE = """The following {chunk_count} partial analyses together cover all \
{record_count} records from the '{model_name}' table, split across chunks for processing.

Synthesize them into one final analysis of the whole dataset.

[Partial analyses]
{summaries_block}
"""

#: Appended to the user prompt on a retry after the model returned unparseable or
#: schema-violating output. ``{error}`` is filled with the specific failure so the model
#: gets concrete, actionable feedback rather than a generic "try again".
JSON_RETRY_HINT = (
    "\n\nYour previous response could not be used: {error}. Return ONLY a single valid "
    "JSON object matching the structure described above, with no other text."
)


def build_structured_audit_prompt(
    model_name: str,
    record_count: int,
    records_json: str,
    field_names: list[str],
) -> tuple[str, str]:
    """Build the structured single-chunk prompt (JSON output).

    The structured counterpart of :func:`build_audit_prompt`: same inputs, but the system
    prompt demands a JSON object matching :class:`~llm_audit.schemas.report.ReportBody`.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    user_prompt = STRUCTURED_AUDIT_TASK_TEMPLATE.format(
        record_count=record_count,
        model_name=model_name,
        field_list=", ".join(field_names),
        records_json=records_json,
    )
    return STRUCTURED_SYSTEM_PROMPT, user_prompt


def build_structured_meta_prompt(
    model_name: str,
    record_count: int,
    chunk_summaries: list[str],
) -> tuple[str, str]:
    """Build the structured reduce-step prompt (JSON output).

    The structured counterpart of :func:`build_meta_prompt`: combines per-chunk prose
    summaries into one validated JSON report instead of more prose.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    summaries_block = "\n\n".join(
        f"--- Partial analysis {i} of {len(chunk_summaries)} ---\n{summary}"
        for i, summary in enumerate(chunk_summaries, start=1)
    )
    user_prompt = STRUCTURED_META_TASK_TEMPLATE.format(
        chunk_count=len(chunk_summaries),
        record_count=record_count,
        model_name=model_name,
        summaries_block=summaries_block,
    )
    return STRUCTURED_META_SYSTEM_PROMPT, user_prompt
