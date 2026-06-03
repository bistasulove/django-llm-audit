"""Token-aware chunking of record lists.

Implemented in M2. Splits a list of records into chunks that each stay under the
configured token threshold, using a fast ``len(text) // 4`` token estimate.
"""


def chunk_records(*args, **kwargs):
    """Placeholder. Implemented in milestone M2."""
    raise NotImplementedError
