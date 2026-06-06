"""A deterministic, offline LLM backend for tests and demos.

Added in M5. ``MockBackend`` implements the full :class:`~llm_audit.backends.base.BaseLLMBackend`
contract but makes no network calls and needs no API key — it returns fixed output. That is
exactly what lets the rest of the plugin (chunking, prompt building, formatting, retry logic,
the management command) be tested without spending money or depending on a live model, per
CLAUDE.md §11: *mock the LLM (an I/O dependency), not the data.*

It ships *inside* the package on purpose — the same way Django ships ``locmem`` email and
cache backends — so downstream users can point ``LLM_AUDIT['BACKEND']`` at it in their own
test settings:

    LLM_AUDIT = {"BACKEND": "llm_audit.backends.mock.MockBackend"}

It is the reusable successor to the ad-hoc fakes that lived in the test suite through M2-M4.

How it decides what to return: the structured path (``--format json``/``markdown``) instructs
the model, via its system prompt, to reply with a *single JSON object*. ``MockBackend``
detects that instruction and returns a valid :class:`~llm_audit.schemas.report.ReportBody`
JSON document; otherwise it returns plain prose. This mirrors the real two-shape behaviour
without any intelligence.
"""

from collections.abc import Generator

from llm_audit.backends.base import BaseLLMBackend
from llm_audit.schemas.report import Anomaly, ReportBody

#: Marker phrase present in the structured system prompts (see ``llm_audit.prompts``). Its
#: presence is how we tell a structured (JSON) call apart from a prose call — the same trick
#: the M4 test fakes used.
_STRUCTURED_MARKER = "single JSON object"

#: A schema-valid body, built from the real model so this mock can never drift out of schema:
#: change ``ReportBody`` incompatibly and this construction fails at import, not at runtime.
_MOCK_BODY = ReportBody(
    headline="Mock headline: this is deterministic output from MockBackend.",
    patterns=[
        "Mock pattern one.",
        "Mock pattern two.",
        "Mock pattern three.",
    ],
    anomalies=[
        Anomaly(
            field="mock_field",
            description="A deterministic placeholder anomaly for testing.",
            severity="low",
        )
    ],
    assessment="This is a fixed assessment produced by MockBackend. No model was called.",
)

#: Prose returned for the free-text path. Multiple words so the streaming split is meaningful.
_MOCK_PROSE = (
    "Mock summary: this deterministic report stands in for a real model response so the "
    "plugin can be tested offline."
)


class MockBackend(BaseLLMBackend):
    """A backend that returns deterministic output without calling any API.

    Accepts the standard backend constructor signature so the
    :func:`~llm_audit.backends.get_backend` factory can build it the same way as the real
    backends, but it ignores every argument — no key, model, or token budget is needed.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None, max_tokens: int = 0):
        # Stored only so callers that read ``backend.model`` (e.g. the command's banner) work
        # uniformly across backends; MockBackend never uses it to produce output.
        self.model = model
        # Recorded so tests can assert what the summarizer asked for, if they want to.
        self.calls: list[tuple[str, str | None]] = []
        self.stream_calls: list[tuple[str, str | None]] = []

    def _reply_for(self, system: str | None) -> str:
        """Return the JSON body for a structured call, else the prose reply."""
        if system and _STRUCTURED_MARKER in system:
            return _MOCK_BODY.model_dump_json()
        return _MOCK_PROSE

    def complete(self, prompt: str, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return self._reply_for(system)

    def stream(self, prompt: str, system: str | None = None) -> Generator[str, None, None]:
        self.stream_calls.append((prompt, system))
        # Yield word by word so consumers see a realistic multi-piece stream rather than one
        # lump. The leading space rides on every word after the first, so the pieces
        # concatenate back to exactly the prose reply: "".join(stream(...)) == complete().
        reply = self._reply_for(system)
        for index, word in enumerate(reply.split(" ")):
            yield word if index == 0 else " " + word
