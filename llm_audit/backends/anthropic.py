"""Anthropic (Claude) LLM backend.

Implemented in M1 (raw call) and refactored to ``BaseLLMBackend`` in M5. Requires the
optional ``anthropic`` dependency: ``pip install django-llm-audit[anthropic]``.
"""

from llm_audit.exceptions import LLMBackendError


class AnthropicBackend:
    """A thin wrapper over the Anthropic Messages API.

    In M1 this is a plain class with a single ``complete`` method — no abstraction.
    M5 refactors it to implement ``BaseLLMBackend`` so the rest of the plugin can
    depend on the abstraction instead of this concrete SDK.
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
