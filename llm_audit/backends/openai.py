"""OpenAI (GPT) LLM backend.

Added in M5 as the second concrete backend. Its whole reason to exist is to *prove the
abstraction*: if the plugin works identically against Anthropic and OpenAI without the
summarizer or command changing, then :class:`~llm_audit.backends.base.BaseLLMBackend` is a
real seam, not a decorative one.

The instructive contrast with :mod:`llm_audit.backends.anthropic`: the ``system`` prompt is
handled differently by each SDK. Anthropic takes it as a top-level ``system`` argument;
OpenAI has no such field — the system prompt is just the first message in the ``messages``
array, with ``role="system"``. Same contract on our side (``complete(prompt, system=...)``),
different shape underneath. Absorbing that difference here is exactly the backend's job.

Requires the optional ``openai`` dependency: ``pip install django-llm-audit[openai]``.
"""

from collections.abc import Generator

from llm_audit.backends.base import BaseLLMBackend
from llm_audit.exceptions import LLMBackendError


class OpenAIBackend(BaseLLMBackend):
    """A thin wrapper over the OpenAI Chat Completions API."""

    def __init__(self, api_key: str, model: str, max_tokens: int):
        if not api_key:
            raise LLMBackendError(
                "No OpenAI API key configured. Set OPENAI_API_KEY in your environment "
                "(or .env) and LLM_AUDIT['API_KEY'] in settings."
            )
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens

    def _build_messages(self, prompt: str, system: str | None) -> list[dict]:
        """Assemble the ``messages`` array.

        Unlike Anthropic, OpenAI carries the system prompt *inside* this array as a
        ``role="system"`` message, prepended before the user turn that holds the data.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Send ``prompt`` to the model and return the full response text.

        Args:
            prompt: The user message content.
            system: Optional system prompt that sets the model's role and rules.

        Returns:
            The model's reply as a plain string.

        Raises:
            LLMBackendError: If the ``openai`` package is missing or the API call fails.
        """
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - exercised manually
            raise LLMBackendError(
                "The 'openai' package is required for OpenAIBackend. "
                "Install it with: pip install django-llm-audit[openai]"
            ) from exc

        client = openai.OpenAI(api_key=self.api_key)

        try:
            response = client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=self._build_messages(prompt, system),
            )
        except openai.OpenAIError as exc:
            raise LLMBackendError(f"OpenAI API call failed: {exc}") from exc

        # The reply is a list of choices; the text lives on the first choice's message.
        return response.choices[0].message.content

    def stream(self, prompt: str, system: str | None = None) -> Generator[str, None, None]:
        """Send ``prompt`` to the model and yield response text as it arrives.

        Like :meth:`AnthropicBackend.stream`, this is a generator: no API call is made until
        the caller starts iterating, so ``LLMBackendError`` here surfaces on first iteration
        rather than when ``stream`` is called, and can fire mid-stream.

        Args:
            prompt: The user message content.
            system: Optional system prompt that sets the model's role and rules.

        Yields:
            Successive pieces of the model's reply, in order.

        Raises:
            LLMBackendError: If the ``openai`` package is missing or the API call fails.
        """
        try:
            import openai
        except ImportError as exc:  # pragma: no cover - exercised manually
            raise LLMBackendError(
                "The 'openai' package is required for OpenAIBackend. "
                "Install it with: pip install django-llm-audit[openai]"
            ) from exc

        client = openai.OpenAI(api_key=self.api_key)

        # Passing stream=True turns the call into an iterator of partial chunks. Each chunk
        # carries a delta; the text lives in choices[0].delta.content, which is None on
        # non-text events (role announcements, the final stop), so we skip those.
        try:
            stream = client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=self._build_messages(prompt, system),
                stream=True,
            )
            for chunk in stream:
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        except openai.OpenAIError as exc:
            raise LLMBackendError(f"OpenAI API streaming call failed: {exc}") from exc
