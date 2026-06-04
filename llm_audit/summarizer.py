"""Summarization orchestration — the map-reduce core of M2.

Takes the records the management command pulled from the ORM and turns them into a single
text summary, transparently handling datasets too large for one LLM call:

* **Map:** split records into token-safe chunks (``chunker``), then summarize each chunk
  independently with the standard audit prompt.
* **Reduce:** combine the per-chunk summaries into one final report with the meta prompt.

When everything fits in a single chunk there is no reduce step — it's just one call, so
small audits pay no map-reduce overhead.

Design notes:

* The backend is **injected**, not constructed here. The orchestrator depends on "a thing
  with ``.complete(prompt, system=...)``", which keeps it provider-agnostic and lets tests
  pass a fake (and M5/M6 a MockBackend). This is the dependency-inversion seam from
  ADR-002, arriving early because map-reduce is the first place it pays off.
* Progress and warnings go through an optional ``notify`` callback rather than ``print``
  or ``self.stdout``. Library code shouldn't own the terminal; the command supplies a
  ``notify`` that writes styled output, while tests can capture the messages in a list.
* Records are serialized **compact** (``indent=None``) for the prompt: indentation is pure
  token waste, and it makes the payload match the chunker's token estimate.
"""

from collections.abc import Callable, Generator

from llm_audit.chunker import chunk_records, estimate_tokens
from llm_audit.prompts import build_audit_prompt, build_meta_prompt
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
) -> str | Generator[str, None, None]:
    """Summarize ``records`` with the LLM, chunking via map-reduce when needed.

    Args:
        records: Non-empty list of record dicts from ``QuerySet.values()``. The caller
            (the management command) is responsible for the empty-queryset guard.
        model_name: The Django model's class name, used to ground the prompts.
        backend: Any object exposing ``complete(prompt, system=...) -> str`` and, for
            ``stream=True``, ``stream(prompt, system=...) -> Generator[str]``.
        token_threshold: Max estimated tokens of records JSON per chunk.
        notify: Optional callback for human-readable progress/warning messages.
        stream: If ``True``, the final user-facing call streams: this function returns a
            generator that yields the report text in pieces. If ``False`` (default) it
            returns the full report as a single string.

    Returns:
        With ``stream=False``, the final summary text. With ``stream=True``, a generator
        yielding that text in pieces.

    Note:
        Streaming only ever applies to the **terminal** call — the single chunk's lone
        call, or the reduce call in a multi-chunk run. The map (per-chunk) calls always
        block, because the reduce step needs each chunk summary's *full* text before it
        can build its prompt. You cannot feed a half-streamed summary onward.
    """
    notify = notify or _noop

    # Every chunk shares the same .values() keys, so compute the field list once. Listing
    # the fields in the prompt tells the model exactly what it has — and what it lacks.
    field_names = list(records[0].keys())

    chunks = chunk_records(records, token_threshold)

    if len(chunks) == 1:
        # Single chunk: the lone map call *is* the terminal call. No reduce step.
        system_prompt, user_prompt = _build_chunk_prompt(
            chunks[0],
            model_name=model_name,
            field_names=field_names,
            token_threshold=token_threshold,
            notify=notify,
        )
    else:
        # Many chunks: map each (always blocking — the reduce step needs each full
        # summary), then build the reduce prompt as the terminal call.
        notify(
            f"Dataset spans {len(chunks)} chunks (~{token_threshold} tokens each); "
            f"summarizing each, then combining."
        )
        chunk_summaries = []
        for index, chunk in enumerate(chunks, start=1):
            notify(f"Summarizing chunk {index}/{len(chunks)} ({len(chunk)} records)...")
            chunk_system, chunk_user = _build_chunk_prompt(
                chunk,
                model_name=model_name,
                field_names=field_names,
                token_threshold=token_threshold,
                notify=notify,
            )
            chunk_summaries.append(backend.complete(chunk_user, system=chunk_system))

        notify("Combining chunk summaries into the final report...")
        system_prompt, user_prompt = build_meta_prompt(
            model_name=model_name,
            record_count=len(records),
            chunk_summaries=chunk_summaries,
        )

    # Exactly one terminal execution point, where the stream-vs-complete decision lives.
    # Everything above already ran (so progress notices fired and any map summaries are
    # in hand); only this final call is allowed to stream to the user.
    if stream:
        return backend.stream(user_prompt, system=system_prompt)
    return backend.complete(user_prompt, system=system_prompt)


def _build_chunk_prompt(
    chunk: list[dict],
    *,
    model_name: str,
    field_names: list[str],
    token_threshold: int,
    notify: Callable[[str], None],
) -> tuple[str, str]:
    """Build the ``(system, user)`` audit prompt for a single chunk (the map step).

    Pure prompt construction — it does **not** call the backend. Separating "what to
    send" from "how to execute it" is what lets :func:`summarize` keep a single terminal
    call where the stream-vs-complete choice is made.
    """
    records_json = serialize_records(chunk, indent=None)

    # Oversized-row warning: the chunker lets a single record bigger than the threshold
    # through as its own chunk (better than failing the run). Surface it here so the user
    # knows this chunk leans on the model's context headroom rather than our budget.
    if len(chunk) == 1 and estimate_tokens(records_json) > token_threshold:
        notify(
            f"One {model_name} record alone exceeds the {token_threshold}-token chunk "
            "threshold; sending it as its own chunk."
        )

    return build_audit_prompt(
        model_name=model_name,
        record_count=len(chunk),
        records_json=records_json,
        field_names=field_names,
    )
