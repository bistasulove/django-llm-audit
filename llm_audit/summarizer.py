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

from collections.abc import Callable

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
) -> str:
    """Summarize ``records`` with the LLM, chunking via map-reduce when needed.

    Args:
        records: Non-empty list of record dicts from ``QuerySet.values()``. The caller
            (the management command) is responsible for the empty-queryset guard.
        model_name: The Django model's class name, used to ground the prompts.
        backend: Any object exposing ``complete(prompt, system=...) -> str``.
        token_threshold: Max estimated tokens of records JSON per chunk.
        notify: Optional callback for human-readable progress/warning messages.

    Returns:
        The final summary text. For a single chunk this is the lone chunk summary; for
        many chunks it is the reduced meta-summary.
    """
    notify = notify or _noop

    # Every chunk shares the same .values() keys, so compute the field list once. Listing
    # the fields in the prompt tells the model exactly what it has — and what it lacks.
    field_names = list(records[0].keys())

    chunks = chunk_records(records, token_threshold)

    # --- Single chunk: no reduce step, just one map call. ---
    if len(chunks) == 1:
        return _summarize_chunk(
            chunks[0],
            model_name=model_name,
            field_names=field_names,
            backend=backend,
            token_threshold=token_threshold,
            notify=notify,
        )

    # --- Many chunks: map each, then reduce. ---
    notify(
        f"Dataset spans {len(chunks)} chunks (~{token_threshold} tokens each); "
        f"summarizing each, then combining."
    )
    chunk_summaries = []
    for index, chunk in enumerate(chunks, start=1):
        notify(f"Summarizing chunk {index}/{len(chunks)} ({len(chunk)} records)...")
        chunk_summaries.append(
            _summarize_chunk(
                chunk,
                model_name=model_name,
                field_names=field_names,
                backend=backend,
                token_threshold=token_threshold,
                notify=notify,
            )
        )

    notify("Combining chunk summaries into the final report...")
    meta_system, meta_user = build_meta_prompt(
        model_name=model_name,
        record_count=len(records),
        chunk_summaries=chunk_summaries,
    )
    return backend.complete(meta_user, system=meta_system)


def _summarize_chunk(
    chunk: list[dict],
    *,
    model_name: str,
    field_names: list[str],
    backend,
    token_threshold: int,
    notify: Callable[[str], None],
) -> str:
    """Summarize a single chunk with the standard audit prompt (the map step)."""
    records_json = serialize_records(chunk, indent=None)

    # Oversized-row warning: the chunker lets a single record bigger than the threshold
    # through as its own chunk (better than failing the run). Surface it here so the user
    # knows this chunk leans on the model's context headroom rather than our budget.
    if len(chunk) == 1 and estimate_tokens(records_json) > token_threshold:
        notify(
            f"One {model_name} record alone exceeds the {token_threshold}-token chunk "
            "threshold; sending it as its own chunk."
        )

    system_prompt, user_prompt = build_audit_prompt(
        model_name=model_name,
        record_count=len(chunk),
        records_json=records_json,
        field_names=field_names,
    )
    return backend.complete(user_prompt, system=system_prompt)
