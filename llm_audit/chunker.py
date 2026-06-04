"""Token-aware chunking of record lists.

Implemented in M2. Splits a list of records into chunks that each stay under a
configured token threshold, so an arbitrarily large dataset can be summarized with the
map-reduce pattern in ``summarizer.py`` instead of being crammed into one API call.

Two ideas from ADR-005 drive this module:

* **Tokens, not records, are the budget.** A fixed ``--limit`` is arbitrary: 50 wide
  rows may blow the context window while 50 narrow rows waste it. We pack by estimated
  token count instead, so the split self-adjusts to how wide each row actually is.
* **A fast estimate is good enough.** ``len(text) // 4`` approximates tokens (~4 chars
  per token for English/JSON). Exact counting needs ``tiktoken`` or a network round-trip;
  we don't need that precision because the threshold sits well below the real context
  window, leaving headroom for the prompt scaffolding that rides on top of the data.

The threshold bounds the **records JSON only** (the per-milestone decision). The system
prompt and task template are roughly fixed and small, and the gap between the threshold
and the model's true context window absorbs them.
"""

from llm_audit.exceptions import ChunkingError
from llm_audit.serializer import serialize_records


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in ``text``.

    Uses the standard ~4-characters-per-token approximation. Deliberately cheap and
    dependency-free; see the module docstring for why this precision is sufficient.

    Args:
        text: The string to estimate.

    Returns:
        Estimated token count (``len(text) // 4``).
    """
    return len(text) // 4


def chunk_records(records: list[dict], token_threshold: int) -> list[list[dict]]:
    """Split ``records`` into chunks that each stay under ``token_threshold``.

    Records are packed greedily: each record is added to the current chunk until the
    next one would push the chunk's estimated token count over the threshold, at which
    point a new chunk is started.

    A single record whose own JSON already exceeds the threshold is emitted as its own
    chunk and allowed through — the real context window is far larger than the
    conservative threshold, so one wide row should never fail the whole run. The
    summarizer is responsible for warning about that case.

    Tokens are estimated from **compact** JSON (``indent=None``) so the estimate matches
    what the summarizer actually sends to the LLM, and so no token budget is wasted on
    indentation whitespace. Estimating per-record slightly overcounts (each record's
    ``[...]`` brackets are counted, though the real payload shares one pair) — a harmless
    bias in the safe direction, since it only makes chunks a touch smaller.

    Args:
        records: The records to chunk, as dicts from ``QuerySet.values()``.
        token_threshold: Maximum estimated tokens of records JSON per chunk. Must be
            positive.

    Returns:
        A list of chunks, each a list of record dicts. Empty input yields ``[]``.

    Raises:
        ChunkingError: If ``token_threshold`` is not a positive integer.
    """
    if token_threshold <= 0:
        raise ChunkingError(f"token_threshold must be a positive integer, got {token_threshold!r}.")

    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = 0

    for record in records:
        record_tokens = estimate_tokens(serialize_records([record], indent=None))

        # If this record won't fit in the (non-empty) current chunk, flush the chunk
        # and start fresh. We only flush a non-empty chunk: when ``current`` is empty
        # and the record is itself oversized, we let it form a lone chunk rather than
        # loop forever — that's the oversized-row path described above.
        if current and current_tokens + record_tokens > token_threshold:
            chunks.append(current)
            current = []
            current_tokens = 0

        current.append(record)
        current_tokens += record_tokens

    if current:
        chunks.append(current)

    return chunks
