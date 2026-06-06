"""Abstract base class for LLM backends.

This is the heart of M5 and the plugin's most important abstraction. Every backend
implements :meth:`complete` and :meth:`stream`, so the rest of the plugin — the
summarizer, the command — depends on *this interface*, never on a concrete provider SDK.
That is the Dependency Inversion Principle: high-level policy (orchestration) and
low-level detail (the Anthropic/OpenAI SDK) both depend on the same abstraction, so we
can swap providers without touching a line of orchestration code.

It is the same pattern Django uses for ``EMAIL_BACKEND``, ``CACHES[...]['BACKEND']`` and
``STORAGES``: a dotted path in settings, resolved to a class at runtime.

The contract here is deliberately small — only what the code actually calls. The
summarizer's single terminal call is either ``complete(prompt, system=...)`` (blocking) or
``stream(prompt, system=...)`` (token-by-token). ``count_tokens`` is not abstract: nothing
in the plugin needs exact token counts yet (chunking uses the ~4-chars-per-token heuristic
in ``chunker.py``), so we give a concrete default rather than force every backend to
implement a method no caller uses. A provider with a real token API can override it later,
the day chunking actually needs exact counts — build the abstraction when you hit the wall,
not before.
"""

from abc import ABC, abstractmethod
from collections.abc import Generator


class BaseLLMBackend(ABC):
    """Interface every LLM backend must implement.

    Subclasses provide :meth:`complete` and :meth:`stream`. The ``system`` argument is the
    optional system prompt that sets the model's role and rules; backends map it to whatever
    their SDK expects (Anthropic takes a top-level ``system``; OpenAI puts it as the first
    message in the ``messages`` array — same contract here, different SDK shape).
    """

    @abstractmethod
    def complete(self, prompt: str, system: str | None = None) -> str:
        """Return the full completion for ``prompt``, blocking until it is ready."""

    @abstractmethod
    def stream(self, prompt: str, system: str | None = None) -> Generator[str, None, None]:
        """Yield pieces of the completion for ``prompt`` as they arrive."""

    def count_tokens(self, text: str) -> int:
        """Estimate the token count of ``text``.

        The default uses the same fast ~4-characters-per-token heuristic as
        :func:`llm_audit.chunker.estimate_tokens`. It is intentionally approximate. A
        backend whose provider exposes an exact token-counting API (Anthropic's token
        endpoint, OpenAI's ``tiktoken``) may override this — but only once a caller needs
        exact counts, which nothing does today.
        """
        return len(text) // 4
