"""Anthropic (Claude) LLM backend.

Implemented in M1 (raw call), gained streaming in M3, and is refactored to
``BaseLLMBackend`` in M5. Requires the optional ``anthropic`` dependency:
``pip install django-llm-audit[anthropic]``.
"""

from collections.abc import Generator

from llm_audit.backends.base import BaseLLMBackend
from llm_audit.exceptions import LLMBackendError


class AnthropicBackend(BaseLLMBackend):
    """A thin wrapper over the Anthropic Messages API.

    Born in M1 as a plain class with a single ``complete`` method — no abstraction. M5
    makes it implement :class:`~llm_audit.backends.base.BaseLLMBackend` so the rest of the
    plugin depends on that interface, not on this concrete SDK. Notably, the method bodies
    did not change: the contract was reverse-engineered from code that has worked since M1,
    which is exactly how it should be — the abstraction describes reality, it doesn't
    reshape it.
    """

    def __init__(self, api_key: str, model: str, max_tokens: int):
        if not api_key:
            raise LLMBackendError(
                "No Anthropic API key configured. Set ANTHROPIC_API_KEY in your "
                "environment (or .env) and LLM_AUDIT['API_KEY'] in settings."
            )
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Send ``prompt`` to Claude and return the full response text.

        Args:
            prompt: The user message content.
            system: Optional system prompt that sets the model's role and rules.

        Returns:
            The model's reply as a plain string.

        Raises:
            LLMBackendError: If the ``anthropic`` package is missing or the API call
                fails.
        """
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised manually in M1
            raise LLMBackendError(
                "The 'anthropic' package is required for AnthropicBackend. "
                "Install it with: pip install django-llm-audit[anthropic]"
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)

        # The Messages API takes structured input: a model, a response-length ceiling
        # (max_tokens is a hard cap, not a target), an optional system prompt, and a
        # list of role/content messages. The data rides in the single user turn.
        request = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            request["system"] = system

        try:
            response = client.messages.create(**request)
        except anthropic.APIError as exc:
            raise LLMBackendError(f"Anthropic API call failed: {exc}") from exc

        # The reply is structured too: a list of content blocks. For a plain text
        # response the text lives in the first block.
        return response.content[0].text

    def stream(self, prompt: str, system: str | None = None) -> Generator[str, None, None]:
        """Send ``prompt`` to Claude and yield response text as it arrives.

        Where :meth:`complete` blocks until the whole reply is ready, this opens a
        streaming connection and yields each incremental piece of text the moment it
        lands. The total latency is the same; the *perceived* responsiveness is far
        better, because the user sees output start almost immediately.

        This is a generator: the body does not run — and no API call is made — until the
        caller starts iterating. A consequence is that ``LLMBackendError`` here surfaces
        on first iteration, not when ``stream`` is called.

        Args:
            prompt: The user message content.
            system: Optional system prompt that sets the model's role and rules.

        Yields:
            Successive pieces of the model's reply, in order.

        Raises:
            LLMBackendError: If the ``anthropic`` package is missing or the API call
                fails.
        """
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - exercised manually
            raise LLMBackendError(
                "The 'anthropic' package is required for AnthropicBackend. "
                "Install it with: pip install django-llm-audit[anthropic]"
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)

        request = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            request["system"] = system

        # client.messages.stream(...) is a context manager that holds the HTTP
        # connection open for the duration of the response. Under the hood the server
        # pushes a sequence of server-sent events; the SDK's .text_stream filters those
        # down to just the text deltas, so we yield plain strings. We re-wrap API errors
        # as LLMBackendError to match complete() — note this can now fire mid-stream,
        # after the caller has already consumed some tokens.
        try:
            with client.messages.stream(**request) as stream:
                yield from stream.text_stream
        except anthropic.APIError as exc:
            raise LLMBackendError(f"Anthropic API streaming call failed: {exc}") from exc
