"""Summarization orchestration — the map-reduce core of M2, structured output in M4.

Takes the records the management command pulled from the ORM and turns them into a
summary, transparently handling datasets too large for one LLM call:

* **Map:** split records into token-safe chunks (``chunker``), then summarize each chunk
  independently with the standard audit prompt.
* **Reduce:** combine the per-chunk summaries into one final report with the meta prompt.

When everything fits in a single chunk there is no reduce step — it's just one call, so
small audits pay no map-reduce overhead.

Two output shapes share this pipeline:

* **Prose** (``structured=False``): free text, optionally streamed (M3). The default.
* **Structured** (``structured=True``): the terminal call must return JSON, which we parse
  and validate against :class:`~llm_audit.schemas.report.ReportBody`, retrying on failure,
  and return as a :class:`~llm_audit.schemas.report.SummaryReport` (M4).

Three design notes carry through both shapes:

* The backend is **injected**, not constructed here (ADR-002 dependency-inversion seam).
* Progress and warnings go through an optional ``notify`` callback, never ``print``.
* Records are serialized **compact** (``indent=None``) so the payload matches the chunker's
  token estimate.

The structured path deliberately reuses the *single terminal execution point*: in a
multi-chunk run the map calls stay prose-and-blocking (their full text feeds the reduce
prompt), and only the final reduce call is asked for JSON. Streaming and structured output
are mutually exclusive — you cannot validate half a JSON object — so ``structured=True``
ignores ``stream``.
"""

import json
from collections.abc import Callable, Generator
from datetime import datetime, timezone

from pydantic import ValidationError

from llm_audit.chunker import chunk_records, estimate_tokens
from llm_audit.exceptions import StructuredOutputError
from llm_audit.prompts import (
    JSON_RETRY_HINT,
    build_audit_prompt,
    build_meta_prompt,
    build_structured_audit_prompt,
    build_structured_meta_prompt,
)
from llm_audit.schemas.report import ReportBody, SummaryReport
from llm_audit.serializer import serialize_records


def _noop(message: str) -> None:
    """Default ``notify`` sink: drop the message."""


def summarize(
    records: list[dict],
    *,
    model_name: str,
    backend,
    token_threshold: int,
    notify: Callable[[str], None] | None = None,
    stream: bool = False,
    structured: bool = False,
    max_retries: int = 2,
) -> str | Generator[str, None, None] | SummaryReport:
    """Summarize ``records`` with the LLM, chunking via map-reduce when needed.

    Args:
        records: Non-empty list of record dicts from ``QuerySet.values()``. The caller
            (the management command) is responsible for the empty-queryset guard.
        model_name: The Django model's class name, used to ground the prompts.
        backend: Any object exposing ``complete(prompt, system=...) -> str`` and, for
            ``stream=True``, ``stream(prompt, system=...) -> Generator[str]``.
        token_threshold: Max estimated tokens of records JSON per chunk.
        notify: Optional callback for human-readable progress/warning messages.
        stream: If ``True`` (and ``structured`` is ``False``), the final call streams: this
            returns a generator yielding the report text in pieces.
        structured: If ``True``, the terminal call must return JSON; the result is a
            validated :class:`SummaryReport`. Takes precedence over ``stream``.
        max_retries: Extra attempts (beyond the first) allowed for the LLM to return valid
            JSON in the structured path. Default 2, i.e. up to 3 attempts total.

    Returns:
        * ``structured=True`` → a :class:`SummaryReport`.
        * ``structured=False, stream=True`` → a generator yielding report text pieces.
        * ``structured=False, stream=False`` → the report text as a single string.

    Raises:
        StructuredOutputError: In the structured path, if the LLM never returns valid,
            schema-conforming JSON within ``max_retries`` retries.

    Note:
        Streaming and the structured JSON path each only ever apply to the **terminal**
        call — the single chunk's lone call, or the reduce call in a multi-chunk run. Map
        (per-chunk) calls always block and return prose, because the reduce step needs each
        chunk summary's *full* text before it can build its prompt.
    """
    notify = notify or _noop

    # Every chunk shares the same .values() keys, so compute the field list once. Listing
    # the fields in the prompt tells the model exactly what it has — and what it lacks.
    field_names = list(records[0].keys())

    chunks = chunk_records(records, token_threshold)

    if len(chunks) == 1:
        # Single chunk: the lone call *is* the terminal call. No reduce step. Its prompt is
        # prose or structured depending on the requested output shape.
        records_json = _serialize_chunk(
            chunks[0], model_name=model_name, token_threshold=token_threshold, notify=notify
        )
        builder = build_structured_audit_prompt if structured else build_audit_prompt
        system_prompt, user_prompt = builder(
            model_name=model_name,
            record_count=len(chunks[0]),
            records_json=records_json,
            field_names=field_names,
        )
    else:
        # Many chunks: map each (always blocking and prose — the reduce step needs each
        # full summary), then build the reduce prompt as the terminal call.
        notify(
            f"Dataset spans {len(chunks)} chunks (~{token_threshold} tokens each); "
            f"summarizing each, then combining."
        )
        chunk_summaries = []
        for index, chunk in enumerate(chunks, start=1):
            notify(f"Summarizing chunk {index}/{len(chunks)} ({len(chunk)} records)...")
            records_json = _serialize_chunk(
                chunk, model_name=model_name, token_threshold=token_threshold, notify=notify
            )
            chunk_system, chunk_user = build_audit_prompt(
                model_name=model_name,
                record_count=len(chunk),
                records_json=records_json,
                field_names=field_names,
            )
            chunk_summaries.append(backend.complete(chunk_user, system=chunk_system))

        notify("Combining chunk summaries into the final report...")
        builder = build_structured_meta_prompt if structured else build_meta_prompt
        system_prompt, user_prompt = builder(
            model_name=model_name,
            record_count=len(records),
            chunk_summaries=chunk_summaries,
        )

    # Exactly one terminal execution point, where the output-shape decision lives.
    # Everything above already ran (progress notices fired, any map summaries are in hand);
    # only this final call streams or is validated.
    if structured:
        return _complete_structured(
            backend,
            system_prompt,
            user_prompt,
            model_name=model_name,
            record_count=len(records),
            notify=notify,
            max_retries=max_retries,
        )
    if stream:
        return backend.stream(user_prompt, system=system_prompt)
    return backend.complete(user_prompt, system=system_prompt)


def _serialize_chunk(
    chunk: list[dict],
    *,
    model_name: str,
    token_threshold: int,
    notify: Callable[[str], None],
) -> str:
    """Serialize a chunk to compact JSON, warning if a lone record overflows the threshold.

    The chunker lets a single record bigger than the threshold through as its own chunk
    (better than failing the run). Surface that here so the user knows this chunk leans on
    the model's context headroom rather than our token budget.
    """
    records_json = serialize_records(chunk, indent=None)
    if len(chunk) == 1 and estimate_tokens(records_json) > token_threshold:
        notify(
            f"One {model_name} record alone exceeds the {token_threshold}-token chunk "
            "threshold; sending it as its own chunk."
        )
    return records_json


def _complete_structured(
    backend,
    system_prompt: str,
    user_prompt: str,
    *,
    model_name: str,
    record_count: int,
    notify: Callable[[str], None],
    max_retries: int,
) -> SummaryReport:
    """Run the terminal call, parse + validate the JSON, and retry on failure.

    LLMs occasionally deviate from an instructed format — a stray code fence, a trailing
    sentence, or a ``severity`` value outside the allowed enum. Rather than trust the
    output blindly, we parse and validate it, and on failure feed the *specific* error back
    to the model and try again. This is the production pattern: never ``json.loads`` raw LLM
    output without a guard, and give the model actionable feedback when it slips.

    Returns:
        A validated :class:`SummaryReport` with our injected metadata.

    Raises:
        StructuredOutputError: If no attempt yields valid, schema-conforming JSON.
    """
    prompt = user_prompt
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        raw = backend.complete(prompt, system=system_prompt)
        try:
            body = _parse_body(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            if attempt < max_retries:
                notify(
                    f"Structured output attempt {attempt + 1} was not valid "
                    f"({_brief(exc)}); retrying with corrective feedback."
                )
                # Re-issue the original task plus targeted feedback about what went wrong.
                prompt = user_prompt + JSON_RETRY_HINT.format(error=_brief(exc))
            continue

        return SummaryReport.from_body(
            body,
            model_name=model_name,
            record_count=record_count,
            generated_at=datetime.now(timezone.utc),
        )

    raise StructuredOutputError(
        f"The LLM did not return valid JSON for the report after "
        f"{max_retries + 1} attempts. Last error: {_brief(last_error)}"
    )


def _parse_body(raw: str) -> ReportBody:
    """Parse raw LLM text into a validated :class:`ReportBody`.

    Strips a surrounding markdown code fence if the model added one despite instructions,
    then ``json.loads`` and validates. Raises ``json.JSONDecodeError`` (bad JSON) or
    ``pydantic.ValidationError`` (valid JSON, wrong shape) for the caller to handle.
    """
    payload = json.loads(_strip_code_fences(raw))
    return ReportBody.model_validate(payload)


def _strip_code_fences(text: str) -> str:
    """Remove a wrapping ```` ``` ```` / ```` ```json ```` fence if the model added one."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    lines = lines[1:]  # drop the opening fence line (``` or ```json)
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]  # drop the closing fence line
    return "\n".join(lines).strip()


def _brief(error: Exception | None) -> str:
    """A short, single-line description of a parse/validation error for prompts and logs."""
    if error is None:
        return "unknown error"
    return " ".join(str(error).split())[:200]
