"""Ollama (local LLM) backend.

This is the CLAUDE.md M5 learning exercise made real: a backend for a provider that has
**no official Python SDK** — you talk to it over plain HTTP. Ollama runs models locally and
exposes a small REST API on ``http://localhost:11434``. There is nothing to ``pip install``
to use it from Python; the request is just JSON over HTTP, which is why this backend leans on
the standard library (:mod:`urllib`) and adds **zero new dependencies**. The only requirement
is that Ollama itself is running (``ollama serve``) with the model pulled (``ollama pull
llama3.1``).

The instructive contrast with the Anthropic and OpenAI backends: those wrap a vendor SDK that
hides the HTTP details. Here we *are* the SDK. We build the request body by hand, POST it, and
parse the response — including Ollama's streaming format, which is **newline-delimited JSON**
(NDJSON): one small JSON object per line, each carrying the next slice of text, ending with a
final object marked ``"done": true``. Reading that stream off the raw HTTP response, line by
line, is the whole lesson.

Like :class:`~llm_audit.backends.mock.MockBackend`, this backend needs **no API key** — a
local server has nothing to authenticate. It accepts the standard ``api_key`` argument (so the
factory can construct it uniformly) and simply ignores it. The host is read from the
``OLLAMA_HOST`` environment variable — the same variable Ollama's own CLI honours — falling
back to ``http://localhost:11434``.

The system/user contract is the same one every backend honours; Ollama's ``/api/chat``
endpoint takes a ``messages`` array, so (like OpenAI) the system prompt becomes the first
message with ``role="system"``, ahead of the user turn that carries the data.
"""

import json
import os
from collections.abc import Generator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from llm_audit.backends.base import BaseLLMBackend
from llm_audit.exceptions import LLMBackendError

#: Where Ollama listens by default. Overridable via the ``OLLAMA_HOST`` environment variable
#: (e.g. ``OLLAMA_HOST=http://192.168.1.10:11434`` to hit a model server on another machine).
DEFAULT_HOST = "http://localhost:11434"


class OllamaBackend(BaseLLMBackend):
    """A backend that talks to a local Ollama server over raw HTTP — no SDK, no API key.

    Args:
        api_key: Accepted for a uniform constructor signature and ignored — a local server
            needs no authentication.
        model: The Ollama model tag to run, e.g. ``"llama3.1"`` or ``"qwen2.5"``. It must
            already be pulled locally (``ollama pull <model>``).
        max_tokens: Response length ceiling, mapped to Ollama's ``options.num_predict``.
    """

    def __init__(self, api_key: str | None = None, model: str = "", max_tokens: int = 1024):
        self.model = model
        self.max_tokens = max_tokens
        # Resolve the host once. We accept a bare ``host:port`` too (Ollama's CLI does), so
        # prepend a scheme if the user left it off, then trim any trailing slash so our path
        # joins are clean.
        host = os.environ.get("OLLAMA_HOST") or DEFAULT_HOST
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        self.host = host.rstrip("/")

    def _build_messages(self, prompt: str, system: str | None) -> list[dict]:
        """Assemble Ollama's ``messages`` array (system first, then the user turn)."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_request(self, prompt: str, system: str | None, *, stream: bool) -> Request:
        """Build the POST request to ``/api/chat`` with a JSON body.

        ``num_predict`` is Ollama's name for the max-tokens cap (its default, 128, is far too
        small for a summary, so we always set it). ``stream`` selects between a single JSON
        response and the NDJSON stream.
        """
        body = json.dumps(
            {
                "model": self.model,
                "messages": self._build_messages(prompt, system),
                "stream": stream,
                "options": {"num_predict": self.max_tokens},
            }
        ).encode("utf-8")
        return Request(
            f"{self.host}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def _unreachable_error(self, exc: URLError) -> LLMBackendError:
        """Turn a connection failure into the actionable 'is it running?' message."""
        return LLMBackendError(
            f"Cannot reach Ollama at {self.host} ({exc.reason}). Is it running? "
            f"Start it with 'ollama serve' and make sure the model is pulled "
            f"('ollama pull {self.model or '<model>'}')."
        )

    def _http_error(self, exc: HTTPError) -> LLMBackendError:
        """Turn an HTTP error response into an LLMBackendError, surfacing Ollama's message.

        Ollama returns useful detail in a JSON body — e.g. a 404 with
        ``{"error": "model 'x' not found, try pulling it first"}`` — so we read it out rather
        than reporting a bare status code.
        """
        detail = ""
        try:
            payload = json.loads(exc.read())
            detail = payload.get("error", "")
        except (ValueError, OSError):  # body wasn't JSON / couldn't be read
            pass
        suffix = f": {detail}" if detail else ""
        return LLMBackendError(f"Ollama API call failed (HTTP {exc.code}){suffix}")

    def complete(self, prompt: str, system: str | None = None) -> str:
        """Send ``prompt`` to the local model and return the full response text.

        Args:
            prompt: The user message content.
            system: Optional system prompt that sets the model's role and rules.

        Returns:
            The model's reply as a plain string.

        Raises:
            LLMBackendError: If Ollama is unreachable or the API call fails.
        """
        request = self._build_request(prompt, system, stream=False)
        try:
            with urlopen(request) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except URLError as exc:  # connection refused, DNS failure, etc.
            raise self._unreachable_error(exc) from exc

        # A non-streamed /api/chat reply is a single JSON object; the text lives in
        # message.content.
        return payload["message"]["content"]

    def stream(self, prompt: str, system: str | None = None) -> Generator[str, None, None]:
        """Send ``prompt`` to the local model and yield response text as it arrives.

        Ollama streams **newline-delimited JSON**: each line is its own JSON object carrying
        the next ``message.content`` slice, until a final object with ``"done": true``. We
        iterate the raw HTTP response line by line and yield each slice. Like the other
        backends' ``stream``, this is a generator, so ``LLMBackendError`` surfaces on first
        iteration and can fire mid-stream.

        Args:
            prompt: The user message content.
            system: Optional system prompt that sets the model's role and rules.

        Yields:
            Successive pieces of the model's reply, in order.

        Raises:
            LLMBackendError: If Ollama is unreachable or the API call fails.
        """
        request = self._build_request(prompt, system, stream=True)
        try:
            with urlopen(request) as response:
                for raw_line in response:
                    line = raw_line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
        except HTTPError as exc:
            raise self._http_error(exc) from exc
        except URLError as exc:
            raise self._unreachable_error(exc) from exc
